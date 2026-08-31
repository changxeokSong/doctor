"""추론용 디바이스 - GPU가 있으면 자동으로 쓴다."""
import torch

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
