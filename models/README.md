# models/ 폴더 구조

**`deployed/`** — 지금 실제로 서비스(Django 백엔드)가 쓰는 모델. `app/config.py`가 가리키는 경로가
전부 이 폴더 안에 있다. 여기 있는 것만 실제로 살아있는 모델이다.

| 폴더 | 역할 | 학습 데이터 |
|---|---|---|
| `model_final` | 분류기(문진단계+세부분류), **klue/roberta-large, lr=1e-5 (2026-07-24 승격)** | 720행(+105 LLM증강), 5-fold CV sub F1 74.4%±3.6%p / 고정 test 103건 sub F1 84.3%(계층필터링 없는 순수 argmax, ISSUE-82) |

**2026-07-25 생성(KoBART) 완전 삭제**: 검색(retriever) 실패 시 KoBART로 답변을 대신 생성하던 폴백을
코드·모델 전부 삭제했다(ISSUE-64 — 반복생성 등 품질 문제가 계속 있었고, "코퍼스에 없는 질문"이라는
사실을 정직하게 보여주는 게 낫다는 판단). `app/models/generator.py`를 삭제했고(코드는
`backups/code_20260725_generator_kobart_removed/`에 백업), `answer_generator_model` 체크포인트는
`experiments/answer_generator_model_deployed_until_20260725_backup`으로 이동했다 — 그래서 지금
`deployed/`에는 분류기 하나만 남아있다.

**2026-07-25 키워드추출 v2/v3 배포 중단**: 키워드 추출이 kiwi 형태소분석(v4) 단독으로 고정되면서
(ISSUE-62 — "형태소 분석기 kiwi로 답변에서 키워드를 추출했다"는 한 문장으로 설명이 끝나는 단일 기법이
설명하기 쉽다는 이유), 학습 기반이던 v2(`keyword_extractor_model`)·v3(`keyword_extractor_model_multispan`)를
`deployed/`에서 뺐다. `app/nlp/keywords.py`·`app/nlp/lexicon.py`(v1~v3+hybrid 코드 전체)도 삭제했다 —
모델 체크포인트는 `experiments/`로 백업 이동, 삭제한 코드는 이 프로젝트가 git 저장소가 아니라서
`backups/code_20260725_keyword_v1v2v3hybrid_removed/`에 파일 그대로 복사해뒀다(복원 방법은 그 안의
README 참고).

**2026-07-24 분류기 교체**: `model_final`이 klue/roberta-base(615행)에서 klue/roberta-large(720행)로
교체됐다. 근거: 5-fold CV에서 sub F1이 기존 대비 통계적으로 유의하게 개선(63.3%→74.4%, p=0.0014,
ISSUE-39)되었고, 속도 저하도 실측상 무시할 수준(분류 12.5ms→23.2ms, +11ms — 파이프라인 전체
~357ms 대비 미미)이었다. 다만 GPU가 이 컴퓨터의 데스크톱·Jupyter와 공유돼(6GB 중 여유가 빠듯) large
전환 직후 GPU 메모리 부족으로 생성기(KoBART)가 "meta tensor" 에러를 낸 사례가 실제로 있었다 —
`app/models/classifier.py`의 `load_model()`에 half precision(`model.half()`, GPU에서만)을 추가해
분류기 메모리를 절반 가까이 줄여 해결(1293.8MB→약 650MB대, 정확도 영향 없음, 추론 전용이라 안전).
기존 base(615행) 체크포인트는 `experiments/model_final_base_615_deployed_until_20260724_backup`으로
백업 이동(삭제 안 함).

**`experiments/`** — 재학습을 시도했지만 기존(위 `deployed/`)을 못 이기거나(head-to-head + CV 검증
결과), 혹은 CV로는 이겼지만 속도 등 추가 검증이 남아 **아직 배포하지 않은** 것들. 전부 보류 상태 —
지우진 않았지만 서비스는 이걸 전혀 안 쓴다.

| 폴더 | 시도 내용 | 결과 |
|---|---|---|
| `model_retrained_20260723` | 분류기, 720행(+105 LLM증강)으로 재학습 | 단일split은 좋아 보였으나 5-fold CV에서 더 나쁨(69.1% vs 63.3%, 통계적 유의성 없음) — 기각 |
| `model_roberta_large_lr2e5_20260726` | 분류기 large, lr만 2e-5로 바꿔 재학습(ISSUE-80·82) | CV 평균은 2e-5가 근소 우세(76.4% vs 74.4%, 유의성 없음)였지만, 실제 배포 기준 고정 test 103건 직접 비교에서는 현재 lr=1e-5가 모든 지표에서 우세(sub macro-F1 84.3% vs 78.4%) — 기각, 배포 유지 |
| `model_final_base_615_deployed_until_20260724_backup` | 2026-07-24 이전까지 배포되던 base(615행) 분류기 백업 | large로 교체되며 보관용으로 이동(성능 열세, ISSUE-39·40) |
| `answer_generator_model_retrained_20260724` | 생성기, 정리된 코퍼스로 재학습 | 반복생성 비율 7.1%→47.7%(6.7배 악화) — 기각 |
| `keyword_extractor_model_retrained_20260724` | 키워드추출 v2, 정리된 3,292행으로 재학습 | exact_match -1.87%p, 무승부 판정 — 기각 |
| `model_final_backup_20260722_unweighted` | 분류기, class-weight 없이 학습(더 이전 실험) | 참고용 백업 |
| `model_weighted` | 분류기, class-weight 실험(더 이전 실험) | 참고용 백업 |

**2026-07-26 koelectra 실험 완전 삭제**: `model_koelectra`(분류기 backbone을
monologg/koelectra-base-v3-discriminator로 교체해본 실험, CV로 재검증된 적 없는 참고용 백업이었음)를
코드·모델·노트북까지 전부 지웠다 — `scripts/training/train_koelectra_model.py`,
`notebooks/train_koelectra_model.ipynb`, `models/experiments/model_koelectra`(430MB) 전부
`backups/code_20260726_koelectra_experiment_removed/`에 그대로 복사해둔 뒤 원본을 삭제했다.

자세한 근거·수치는 `reports/project_manual_20260724.html`의 "학습 방법론 상세"·"방법론적 엄밀성"
섹션과 `reports/progress_log.html`(ISSUE-21, ISSUE-23, ISSUE-24) 참고.
