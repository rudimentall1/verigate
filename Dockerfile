FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/keys

ENV VERIGATE_POLICY=/app/policies/default.yaml \
    VERIGATE_DB=/app/data/verigate.db \
    VERIGATE_PRIVATE_KEY=/app/keys/issuer.key \
    VERIGATE_PUBLIC_KEY=/app/keys/issuer.pub \
    VERIGATE_ENV=production \
    VERIGATE_REQUIRE_AUTH=1 \
    VERIGATE_REQUIRE_SIGNED_INTENT=1 \
    VERIGATE_REQUIRE_ENCRYPTED_KEY=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
