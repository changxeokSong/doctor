"""kiwi 형태소분석 기반, 학습 데이터가 필요 없는 기능들 모음:
v4 키워드 추출, 품사별 분석 화면, '내용어 없는 부정 표현' 판정.
전부 특정 단어를 하드코딩한 목록이 아니라 kiwi 품사 태그를 기준으로 판단한다."""
from functools import lru_cache

from kiwipiepy import Kiwi

# kiwi 기본 사전은 통증의학과 전문 용어(복합어)를 형태소 여러 개로 억지로 쪼갠다
# (예: "신경차단술" -> 신경/차단/술). 조각나도 각 조각이 그 자체로 의미 있는 단어면 안 합치고,
# 혼자 있으면 의미가 안 통하는 조각만 등록했다(예: "경막"+"외", "신경"+"차단"+"술"의 "술").
_USER_WORDS = [
    "경막외신경차단술", "신경차단술", "경막외", "근이완제", "척추관협착증", "대상포진후신경통",
    "후관절증후군", "요추간판탈출증", "근막통증증후군", "체외충격파",
]
_USER_WORDS_SET = set(_USER_WORDS)
# add_user_word()는 공백 없이 붙어 있어야만 인식한다 - 띄어쓰기 실수로 조각난 토큰을 다시 합치는
# 보정은 아래 _merge_registered_compounds()가 한다.
_COMPOUND_MERGE_TAGS = {"NNG", "NNP", "XR", "NNB", "MM", "SL", "SH"}
_MAX_COMPOUND_WORD_LEN = max(len(w) for w in _USER_WORDS)


@lru_cache(maxsize=None)
def get_kiwi() -> Kiwi:
    kiwi = Kiwi()
    for word in _USER_WORDS:
        kiwi.add_user_word(word, "NNG")
    return kiwi


def _merge_registered_compounds(toks: list) -> list:
    """연속된 명사류/관형사 토큰을 이어붙였을 때 _USER_WORDS와 정확히 일치하면 하나의 토큰으로
    합친다 - 등록된 단어 목록과 정확히 일치할 때만 합치므로(닫힌 화이트리스트), 다른 단어가
    우연히 잘못 합쳐질 위험은 없다."""
    merged = []
    i, n = 0, len(toks)
    while i < n:
        matched = False
        max_j = min(n, i + _MAX_COMPOUND_WORD_LEN)
        for j in range(max_j, i + 1, -1):  # 가장 긴 조합부터 시도
            candidates = toks[i:j]
            if not all(t.tag in _COMPOUND_MERGE_TAGS for t in candidates):
                continue
            combo = "".join(t.form for t in candidates)
            if combo in _USER_WORDS_SET:
                first, last = candidates[0], candidates[-1]
                merged.append(_MergedTok(combo, "NNG", first.start, last.start + last.len - first.start))
                i = j
                matched = True
                break
        if not matched:
            merged.append(toks[i])
            i += 1
    return merged


class _MergedTok:
    """kiwipiepy Token과 같은 인터페이스(form/tag/start/len)만 흉내내는 경량 대역 - 실제 Token은
    직접 생성할 수 없어서 대신 만든다."""
    __slots__ = ("form", "tag", "start", "len")

    def __init__(self, form, tag, start, length):
        self.form = form
        self.tag = tag
        self.start = start
        self.len = length


_KIWI_KEEP_TAGS = {"NNG", "NNP", "XR", "SN", "NR", "MAG"}  # 용언(동사/형용사)은 아래에서 태그 접두어로 별도 처리
_KIWI_PREDICATE_PREFIXES = ("VA", "VV")  # VA/VA-I(형용사), VV/VV-I(동사) - "쑤시다·붓다·당기다" 등 증상 서술어 포함
# MAG(일반부사)는 임상적으로 의미 있는 것("자주"/"가끔")과 정도만 강조하는 것("너무"/"좀")이 같은
# 태그로 묶여 태그만으로 구분이 안 된다. 정도부사는 닫힌 집합이라 예외로 뺀다.
_KIWI_DROP_FORMS = {
    "있", "받", "것", "적", "수", "하",
    "너무", "좀", "진짜", "정말", "되게", "매우", "아주", "완전", "약간", "조금",
}


_NEGATION_ADVERBS = {"안", "못"}  # "안 하다"/"못 하다" 둘뿐인 닫힌 집합이라 하드코딩해도 일반성은 안 깨짐.
# "안"/"못"만 따로 떼어 키워드로 뽑으면 부정 의미가 사라져 원문과 반대로 읽힐 수 있다.
_TRAILING_PUNCT = ".?!,·…\"'”’"


def _eojeol_span(text: str, pos: int) -> tuple:
    """pos(문자 인덱스)를 포함하는 공백 구분 어절의 (start, end)를 찾는다(끝의 문장부호는 제외).
    용언 불규칙활용은 형태소 경계가 표면형과 안 맞아서, 토큰 하나의 start/len보다 어절 전체를
    강조 범위로 쓰는 게 더 안정적이다."""
    start = text.rfind(" ", 0, pos) + 1
    end = text.find(" ", pos)
    if end == -1:
        end = len(text)
    while end > start and text[end - 1] in _TRAILING_PUNCT:
        end -= 1
    return start, end


def _match_ji_negation(toks: list, j: int):
    """toks[j]가 "지"(EC) 바로 다음 위치일 때, 그 뒤에서 부정 보조용언("않다"/"말다"/"못하다")을
    찾는다. "지"와 부정 보조용언 사이에 보조사가 하나 끼는 경우도 건너뛴다(예: "아프지도 않고").
    찾으면 (합쳐서 쓸 접미어, 부정 부분 마지막 토큰의 인덱스)를, 없으면 None을 돌려준다."""
    if j < len(toks) and toks[j].tag == "JX":
        j += 1
    if j >= len(toks):
        return None
    t = toks[j]
    if t.tag == "VX" and t.form in ("않", "말"):
        return "지" + t.form + "다", j
    if t.tag == "MAG" and t.form == "못" and j + 1 < len(toks) and toks[j + 1].form == "하":
        return "지못하다", j + 1
    return None


def extract_keywords_morphological_spans(answer: str) -> list:
    """v4 키워드를 (표제어(다형), 원문 시작offset, 원문 끝offset)로 반환한다 - 하이라이트용.
    명사류는 토큰 자체의 정확한 위치를, 용언(동사/형용사)은 불규칙활용 때문에 어절 전체 범위를
    쓴다. 반환 순서는 "명사 먼저, 용언은 그 뒤"로 정렬하고 같은 그룹 안에서는 등장 순서를
    유지한다(안정 정렬). "안"/"못" 부정부사와 "-지 않다"/"-지 못하다" 부정 보조용언은 바로 옆
    용언과 합쳐 하나의 키워드로 낸다(따로 떼면 부정 의미가 사라짐). 숫자(SN)는 바로 뒤 단위
    의존명사(NNB)와 결합한다(예: "7점") - 단위 없는 숫자만 남으면 의미가 없어지기 때문."""
    kiwi = get_kiwi()
    toks = _merge_registered_compounds(list(kiwi.tokenize(answer)))
    out = []
    spans = {}
    i = 0
    while i < len(toks):
        tok = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        has_adj_suffix = nxt is not None and nxt.tag.startswith("XSA")
        is_predicate = tok.tag.startswith(_KIWI_PREDICATE_PREFIXES)

        # "안"/"못" + 용언 -> "안먹다"처럼 하나의 키워드로 합쳐 부정 의미를 지킨다.
        if tok.tag == "MAG" and tok.form in _NEGATION_ADVERBS and nxt is not None \
                and nxt.tag.startswith(_KIWI_PREDICATE_PREFIXES):
            combo = tok.form + nxt.form + "다"
            if combo not in out:
                out.append(combo)
                start = _eojeol_span(answer, tok.start)[0]
                end = _eojeol_span(answer, nxt.start)[1]
                spans[combo] = (start, end)
            i += 2
            continue

        # 용언 + "-지 않다"/"-지 못하다"/"-지 말다" -> 부정 보조용언까지 하나로 합친다.
        if is_predicate and nxt is not None and nxt.tag == "EC" and nxt.form == "지":
            neg = _match_ji_negation(toks, i + 2)
            if neg is not None:
                suffix, end_idx = neg
                combo = tok.form + suffix
                if combo not in out:
                    out.append(combo)
                    start = _eojeol_span(answer, tok.start)[0]
                    end = _eojeol_span(answer, toks[end_idx].start)[1]
                    spans[combo] = (start, end)
                i = end_idx + 1
                continue

        # 숫자(SN) + 단위 의존명사(NNB) 결합 - NNB는 "것"/"수"처럼 의미 없는 것도 많아 숫자 바로
        # 뒤에 오는 경우만 단위로 인정한다.
        if tok.tag == "SN" and nxt is not None and nxt.tag == "NNB":
            combo = tok.form + nxt.form
            if combo not in out:
                out.append(combo)
                spans[combo] = (tok.start, nxt.start + nxt.len)
            i += 2
            continue

        # 명사류+형용사파생접미사(XSA)는 결합형만 낸다(어근과 결합형 중복 방지).
        # 명사+동사파생접미사(XSV)는 반대로 결합하지 않고 명사만 낸다 - 명사 자체가 사전 표제어라
        # 합치면 매칭이 깨지기 때문(has_adj_suffix가 XSA만 보므로 XSV는 이 분기를 안 탐).
        if tok.tag in _KIWI_KEEP_TAGS and tok.form not in _KIWI_DROP_FORMS and has_adj_suffix:
            combo = tok.form + nxt.form + "다"
            if combo not in out:
                out.append(combo)
                spans[combo] = _eojeol_span(answer, tok.start)
            i += 2
            continue

        if tok.tag in _KIWI_KEEP_TAGS and tok.form not in _KIWI_DROP_FORMS:
            if tok.form not in out:
                out.append(tok.form)
                spans[tok.form] = (tok.start, tok.start + tok.len)
        elif is_predicate and tok.form not in _KIWI_DROP_FORMS:
            form = tok.form + "다"
            if form not in out:
                out.append(form)
                spans[form] = _eojeol_span(answer, tok.start)
        i += 1
    out = sorted(out, key=lambda form: not has_noun(form))
    return [(form, spans[form][0], spans[form][1]) for form in out]


def extract_keywords_morphological(answer: str) -> list:
    """형태소분석 기반(v4, 학습 불필요) - 명사/형용사/동사/어근만 추출, 조사·의존명사·가벼운 동사는 제외.
    용언 어간은 원형(다형)으로 복원한다(예: "아프"->"아프다"). 어근(XR)+형용사파생접미사(XSA)
    결합도 복원한다(예: "뻐근"+"하"->"뻐근하다"). 명사+동사파생접미사(XSV)는 결합하지 않는다 -
    명사 자체가 독립된 사전 표제어이므로 결합하면 매칭이 깨진다."""
    return [form for form, _, _ in extract_keywords_morphological_spans(answer)]


# 세종/klue 계열 품사 태그(kiwi 기준) -> 한글 표시명. "-I"/"-R" 등 불규칙활용 접미는 base tag로 통일해서 찾는다.
_KIWI_TAG_LABELS = {
    "NNG": "일반명사", "NNP": "고유명사", "NNB": "의존명사", "NR": "수사", "NP": "대명사",
    "VV": "동사", "VA": "형용사", "VX": "보조용언", "VCP": "긍정지정사(이다)", "VCN": "부정지정사(아니다)",
    "MM": "관형사", "MAG": "일반부사", "MAJ": "접속부사",
    "IC": "감탄사",
    "JKS": "주격조사", "JKC": "보격조사", "JKG": "관형격조사", "JKO": "목적격조사",
    "JKB": "부사격조사", "JKV": "호격조사", "JKQ": "인용격조사", "JX": "보조사", "JC": "접속조사",
    "EP": "선어말어미", "EF": "종결어미", "EC": "연결어미", "ETN": "명사형전성어미", "ETM": "관형형전성어미",
    "XPN": "체언접두사", "XSN": "명사파생접미사", "XSV": "동사파생접미사", "XSA": "형용사파생접미사",
    "XSM": "부사파생접미사", "XR": "어근",
    "SF": "마침표류", "SP": "쉼표류", "SS": "괄호/따옴표", "SSO": "여는괄호/따옴표", "SSC": "닫는괄호/따옴표",
    "SE": "줄임표", "SO": "붙임표", "SW": "기타기호",
    "SL": "외국어(알파벳)", "SH": "한자", "SN": "숫자", "SB": "순서기호",
    "UN": "분석불능",
    # 웹(W_*)·기타(Z_*, USER0~4)는 세종 표준 태그셋이 아니라 kiwi 확장 태그. 문진 답변엔 거의 안
    # 나오지만, 나오더라도 태그 코드 원문이 그대로 노출되지 않게 대비해둔다.
    "W_URL": "URL", "W_EMAIL": "이메일", "W_HASHTAG": "해시태그", "W_MENTION": "멘션",
    "W_SERIAL": "일련번호", "W_EMOJI": "이모지",
    "Z_CODA": "덧붙은 받침", "Z_SIOT": "사이시옷",
    "USER0": "사용자정의0", "USER1": "사용자정의1", "USER2": "사용자정의2", "USER3": "사용자정의3",
    "USER4": "사용자정의4",
}
# 큰 분류(품사 대분류) 묶음 - 명사/동사·형용사/부사·관형사/조사/어미/기타
_KIWI_TAG_GROUPS = {
    "체언(명사류)": ("NNG", "NNP", "NNB", "NR", "NP"),
    "용언(동사·형용사)": ("VV", "VA", "VX", "VCP", "VCN"),
    "수식언(관형사·부사)": ("MM", "MAG", "MAJ"),
    "독립언(감탄사)": ("IC",),
    "관계언(조사)": ("JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC"),
    "어미·접사": ("EP", "EF", "EC", "ETN", "ETM", "XPN", "XSN", "XSV", "XSA", "XSM", "XR"),
}


def _tag_base(tag: str) -> str:
    return tag.split("-")[0]


def _tag_label(tag: str) -> str:
    return _KIWI_TAG_LABELS.get(_tag_base(tag), tag)


def _tag_group(tag: str) -> str:
    base = _tag_base(tag)
    for group, tags in _KIWI_TAG_GROUPS.items():
        if base in tags:
            return group
    return "기타(기호·외래어 등)"


def pos_breakdown(text: str) -> list:
    """문장을 형태소 단위로 쪼개 (형태, 태그, 한글 품사명, 대분류)를 반환한다 - 조사·어미까지
    포함하는 원시 분석 결과. 기본 화면은 pos_breakdown_simple을 쓴다."""
    kiwi = get_kiwi()
    return [
        {"form": t.form, "tag": t.tag, "label": _tag_label(t.tag), "group": _tag_group(t.tag)}
        for t in kiwi.tokenize(text)
    ]


def pos_breakdown_simple(text: str) -> dict:
    """조사·어미는 빼고, 명사와 용언(동사·형용사·보조용언)만 사전형(다형)으로 정리한다.
    "아프"가 아니라 "아프다"처럼 완전한 단어 형태로 표시한다."""
    kiwi = get_kiwi()
    toks = list(kiwi.tokenize(text))
    groups = {"명사": [], "동사·형용사·보조용언": []}
    i = 0
    while i < len(toks):
        tok = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        base = _tag_base(tok.tag)
        has_adj_suffix = nxt is not None and nxt.tag.startswith("XSA")
        if base == "XR" and has_adj_suffix:
            form = tok.form + nxt.form + "다"
            if form not in groups["동사·형용사·보조용언"]:
                groups["동사·형용사·보조용언"].append(form)
            i += 2
            continue
        if base in ("NNG", "NNP", "NNB", "NR", "NP"):
            if tok.form not in groups["명사"]:
                groups["명사"].append(tok.form)
            if has_adj_suffix:
                form = tok.form + nxt.form + "다"
                if form not in groups["동사·형용사·보조용언"]:
                    groups["동사·형용사·보조용언"].append(form)
                i += 2
                continue
        elif base in ("VV", "VA", "VX", "VCP", "VCN"):
            form = tok.form + "다"
            if form not in groups["동사·형용사·보조용언"]:
                groups["동사·형용사·보조용언"].append(form)
        i += 1
    return groups


def has_noun(kw: str) -> bool:
    """kw 안에 명사류(NNG/NNP/XR/SN/NR)가 하나라도 있으면 True. 키워드 정렬 시 "무엇이"(명사)를
    "어떻다"(동사/형용사)보다 앞세우는 데 쓴다."""
    kw = kw.strip()
    if not kw:
        return False
    kiwi = get_kiwi()
    toks = list(kiwi.tokenize(kw))
    return any(t.tag in ("NNG", "NNP", "XR", "SN", "NR") for t in toks)


_PARTICLE_TAGS = {"JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC"}


def strip_trailing_particle(text: str) -> str:
    """문자 offset으로 잘라낸 span 끝에 조사가 딸려 나온 경우(예: "무릎이" -> "무릎")를 보정한다."""
    text = text.strip()
    if not text:
        return text
    kiwi = get_kiwi()
    toks = list(kiwi.tokenize(text))
    if not toks:
        return text
    last = toks[-1]
    if last.tag in _PARTICLE_TAGS and last.start > 0:
        return text[:last.start].rstrip()
    return text


def strip_filler_adverbs(text: str) -> str:
    """예측된 span 맨 앞/뒤에 정도부사(_KIWI_DROP_FORMS)가 붙어 나온 경우를 잘라낸다
    (예: "더 심해졌습니다" -> "심해졌습니다"). 문장 중간에 낀 경우는 구조를 해칠 수 있어
    건드리지 않고 맨 앞/뒤만 반복 제거한다."""
    kiwi = get_kiwi()
    toks = list(kiwi.tokenize(text))
    if not toks:
        return text
    start_i, end_i = 0, len(toks)
    while start_i < end_i and toks[start_i].tag == "MAG" and toks[start_i].form in _KIWI_DROP_FORMS:
        start_i += 1
    while end_i > start_i and toks[end_i - 1].tag == "MAG" and toks[end_i - 1].form in _KIWI_DROP_FORMS:
        end_i -= 1
    if start_i == 0 and end_i == len(toks):
        return text
    if start_i >= end_i:
        return text
    start = toks[start_i].start
    last = toks[end_i - 1]
    end = last.start + last.len
    return text[start:end].strip()
