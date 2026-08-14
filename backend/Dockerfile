FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# PyTorch'u önce CPU-only sürümüyle kur. Varsayılan PyPI paketi Linux'ta
# ~2 GB NVIDIA CUDA kütüphanesi çekiyor (cublas, cudnn, nccl, triton...);
# sunucuda ekran kartı olmadığı için hiçbiri kullanılmıyor. Bu satır olmadan
# imaj gereksiz yere birkaç GB büyüyor ve build dakikalarca uzuyor.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
