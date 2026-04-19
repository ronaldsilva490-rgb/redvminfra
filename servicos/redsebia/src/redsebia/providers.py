import base64
import json
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


def cents_to_brl(cents: int) -> float:
    return round(int(cents) / 100.0, 2)


def fake_qr_svg(label: str) -> str:
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">
      <rect width="320" height="320" fill="#120404"/>
      <rect x="20" y="20" width="280" height="280" rx="16" fill="#1d0606" stroke="#db2315" stroke-width="4"/>
      <text x="160" y="142" text-anchor="middle" font-size="24" fill="#ffffff" font-family="Arial">REDSEBIA</text>
      <text x="160" y="184" text-anchor="middle" font-size="16" fill="#ffb6aa" font-family="Arial">{label}</text>
    </svg>
    """.strip()
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


@dataclass
class ChargeRequest:
    charge_id: str
    user: dict[str, Any]
    amount_cents: int
    description: str
    public_base_url: str


class PaymentProvider(ABC):
    code: str
    name: str
    docs_url: str
    supported_methods: list[str]
    implemented: bool = True
    config_fields: list[dict[str, Any]]

    def metadata(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "docs_url": self.docs_url,
            "supported_methods": self.supported_methods,
            "implemented": self.implemented,
            "config_fields": self.config_fields,
        }

    @abstractmethod
    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        raise NotImplementedError

    async def refresh_charge(self, config: dict[str, Any], charge: dict[str, Any]) -> dict[str, Any] | None:
        return None

    async def handle_webhook(self, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        return None


class SandboxPixProvider(PaymentProvider):
    code = "sandbox_pix"
    name = "Sandbox PIX"
    docs_url = ""
    supported_methods = ["pix"]
    config_fields = [
        {"name": "auto_credit", "label": "Auto creditar apos criar", "type": "checkbox", "placeholder": ""},
    ]

    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        label = f"PIX sandbox R$ {cents_to_brl(request.amount_cents):.2f}"
        return {
            "provider_charge_id": f"sandbox_{request.charge_id}",
            "status": "pending",
            "qr_code": f"sandboxpix://pay/{request.charge_id}",
            "qr_code_base64": fake_qr_svg(label),
            "payment_url": "",
            "expires_at": time.time() + 60 * 30,
            "payload": {
                "sandbox": True,
                "copy_paste": f"0002012658redsebia-sandbox/{request.charge_id}",
            },
        }


class ManualPixProvider(PaymentProvider):
    code = "manual_pix"
    name = "PIX Manual"
    docs_url = ""
    supported_methods = ["pix"]
    config_fields = [
        {"name": "pix_key", "label": "Chave PIX", "type": "text", "placeholder": "sua-chave-pix"},
        {"name": "recipient_name", "label": "Recebedor", "type": "text", "placeholder": "RED Systems"},
        {"name": "bank_name", "label": "Banco", "type": "text", "placeholder": "Banco"},
        {"name": "instructions", "label": "Instrucoes", "type": "textarea", "placeholder": "Envie o comprovante pelo suporte."},
    ]

    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        key = str(config.get("pix_key") or "").strip()
        if not key:
            raise ValueError("Configure a chave PIX no painel administrativo.")
        label = str(config.get("recipient_name") or "RED Systems")
        amount = cents_to_brl(request.amount_cents)
        return {
            "provider_charge_id": f"manual_{request.charge_id}",
            "status": "pending",
            "qr_code": key,
            "qr_code_base64": fake_qr_svg(f"PIX manual R$ {amount:.2f}"),
            "payment_url": "",
            "expires_at": time.time() + 60 * 60 * 24,
            "payload": {
                "pix_key": key,
                "recipient_name": label,
                "bank_name": str(config.get("bank_name") or ""),
                "instructions": str(config.get("instructions") or ""),
            },
        }


class AsaasProvider(PaymentProvider):
    code = "asaas"
    name = "Asaas"
    docs_url = "https://docs.asaas.com/docs/cobrancas-via-pix"
    supported_methods = ["pix", "boleto", "credit_card"]
    config_fields = [
        {"name": "environment", "label": "Ambiente", "type": "select", "options": ["sandbox", "production"]},
        {"name": "api_key", "label": "API Key", "type": "password", "placeholder": "$aact_..."},
    ]

    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("Configure a API Key do Asaas.")
        env = str(config.get("environment") or "sandbox").strip().lower()
        base = "https://api-sandbox.asaas.com" if env != "production" else "https://api.asaas.com"
        headers = {"accept": "application/json", "content-type": "application/json", "access_token": api_key}
        async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
            customer = await self._ensure_customer(client, api_key, request.user)
            due_date = time.strftime("%Y-%m-%d", time.localtime(time.time() + 60 * 60 * 24))
            payment_resp = await client.post(
                "/v3/payments",
                headers=headers,
                json={
                    "customer": customer,
                    "billingType": "PIX",
                    "value": cents_to_brl(request.amount_cents),
                    "dueDate": due_date,
                    "description": request.description,
                    "externalReference": request.charge_id,
                },
            )
            payment_resp.raise_for_status()
            payment_data = payment_resp.json()
            pix_resp = await client.get(f"/v3/payments/{payment_data['id']}/pixQrCode", headers=headers)
            pix_resp.raise_for_status()
            pix_data = pix_resp.json()
        return {
            "provider_charge_id": payment_data["id"],
            "status": "pending",
            "external_reference": request.charge_id,
            "qr_code": pix_data.get("payload") or "",
            "qr_code_base64": f"data:image/png;base64,{pix_data.get('encodedImage')}" if pix_data.get("encodedImage") else "",
            "payment_url": payment_data.get("invoiceUrl") or "",
            "expires_at": self._parse_asaas_expiration(pix_data.get("expirationDate")),
            "payload": {"payment": payment_data, "pix": pix_data},
        }

    async def refresh_charge(self, config: dict[str, Any], charge: dict[str, Any]) -> dict[str, Any] | None:
        api_key = str(config.get("api_key") or "").strip()
        if not api_key or not charge.get("provider_charge_id"):
            return None
        env = str(config.get("environment") or "sandbox").strip().lower()
        base = "https://api-sandbox.asaas.com" if env != "production" else "https://api.asaas.com"
        headers = {"accept": "application/json", "access_token": api_key}
        async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
            resp = await client.get(f"/v3/payments/{charge['provider_charge_id']}", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        status_map = {
            "RECEIVED": "paid",
            "CONFIRMED": "paid",
            "RECEIVED_IN_CASH": "paid",
            "PENDING": "pending",
            "OVERDUE": "expired",
        }
        return {"status": status_map.get(str(data.get("status") or "").upper(), "pending"), "payload": {"payment": data}}

    async def handle_webhook(self, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        payment = payload.get("payment") or {}
        payment_id = payment.get("id")
        if not payment_id:
            return None
        event = str(payload.get("event") or "")
        status = "pending"
        if event in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}:
            status = "paid"
        return {"provider_charge_id": payment_id, "status": status, "payload": {"webhook": payload}}

    async def _ensure_customer(self, client: httpx.AsyncClient, api_key: str, user: dict[str, Any]) -> str:
        # Asaas accepts creating customers repeatedly; the simplest stable path for now is isolated customer per request.
        response = await client.post(
            "/v3/customers",
            headers={"accept": "application/json", "content-type": "application/json", "access_token": api_key},
            json={
                "name": user["name"],
                "email": user["email"],
                "cpfCnpj": user.get("cpf") or None,
                "notificationDisabled": True,
            },
        )
        response.raise_for_status()
        return response.json()["id"]

    @staticmethod
    def _parse_asaas_expiration(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return time.mktime(time.strptime(value[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            return None


class EfiPixProvider(PaymentProvider):
    code = "efi_pix"
    name = "Efí Bank PIX"
    docs_url = "https://dev.efipay.com.br/docs/api-pix/cobrancas-imediatas"
    supported_methods = ["pix"]
    config_fields = [
        {"name": "environment", "label": "Ambiente", "type": "select", "options": ["homolog", "production"]},
        {"name": "client_id", "label": "Client ID", "type": "text", "placeholder": "client-id"},
        {"name": "client_secret", "label": "Client Secret", "type": "password", "placeholder": "client-secret"},
        {"name": "certificate_p12_base64", "label": "Certificado P12 em Base64", "type": "textarea", "placeholder": "base64 do certificado .p12"},
    ]

    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        auth = await self._authorize(config)
        base = auth["base_url"]
        headers = {"Authorization": f"Bearer {auth['access_token']}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(base_url=base, timeout=40.0, cert=auth["cert"]) as client:
            cob_resp = await client.post(
                "/v2/cob",
                headers=headers,
                json={
                    "calendario": {"expiracao": 3600},
                    "valor": {"original": f"{cents_to_brl(request.amount_cents):.2f}"},
                    "solicitacaoPagador": request.description,
                },
            )
            cob_resp.raise_for_status()
            cob_data = cob_resp.json()
            loc_id = ((cob_data.get("loc") or {}).get("id")) or None
            qr_data = {}
            if loc_id:
                qr_resp = await client.get(f"/v2/loc/{loc_id}/qrcode", headers=headers)
                qr_resp.raise_for_status()
                qr_data = qr_resp.json()
        return {
            "provider_charge_id": cob_data.get("txid") or request.charge_id,
            "status": "pending",
            "external_reference": request.charge_id,
            "qr_code": qr_data.get("qrcode") or cob_data.get("pixCopiaECola") or "",
            "qr_code_base64": qr_data.get("imagemQrcode") or "",
            "payment_url": qr_data.get("linkVisualizacao") or "",
            "expires_at": time.time() + 3600,
            "payload": {"cob": cob_data, "qr": qr_data},
        }

    async def handle_webhook(self, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        pix_list = payload.get("pix") or []
        if not pix_list:
            return None
        pix_item = pix_list[0]
        txid = pix_item.get("txid")
        if not txid:
            return None
        return {"provider_charge_id": txid, "status": "paid", "payload": {"webhook": payload}}

    async def _authorize(self, config: dict[str, Any]) -> dict[str, Any]:
        env = str(config.get("environment") or "homolog").strip().lower()
        base_url = "https://pix.api.efipay.com.br" if env == "production" else "https://pix-h.api.efipay.com.br"
        client_id = str(config.get("client_id") or "").strip()
        client_secret = str(config.get("client_secret") or "").strip()
        cert_b64 = str(config.get("certificate_p12_base64") or "").strip()
        if not (client_id and client_secret and cert_b64):
            raise ValueError("Configure client_id, client_secret e o certificado P12 Base64 da Efí.")
        cert_tuple = _p12_base64_to_pem_pair(cert_b64, "")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0, cert=cert_tuple) as client:
            resp = await client.post(
                "/oauth/token",
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
                json={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            data = resp.json()
        return {"base_url": base_url, "access_token": data["access_token"], "cert": cert_tuple}


class MercadoPagoPixProvider(PaymentProvider):
    code = "mercadopago_pix"
    name = "Mercado Pago PIX"
    docs_url = "https://www.mercadopago.com.br/developers/pt/docs/checkout-api-payments/integration-configuration/integrate-pix"
    supported_methods = ["pix"]
    config_fields = [
        {"name": "environment", "label": "Ambiente", "type": "select", "options": ["sandbox", "production"]},
        {"name": "access_token", "label": "Access Token", "type": "password", "placeholder": "APP_USR-..."},
    ]

    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        token = str(config.get("access_token") or "").strip()
        if not token:
            raise ValueError("Configure o access_token do Mercado Pago.")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": str(uuid.uuid4()),
        }
        async with httpx.AsyncClient(base_url="https://api.mercadopago.com", timeout=30.0) as client:
            resp = await client.post(
                "/v1/payments",
                headers=headers,
                json={
                    "transaction_amount": cents_to_brl(request.amount_cents),
                    "description": request.description,
                    "payment_method_id": "pix",
                    "payer": {"email": request.user["email"]},
                    "external_reference": request.charge_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        tx = ((data.get("point_of_interaction") or {}).get("transaction_data")) or {}
        return {
            "provider_charge_id": str(data.get("id") or request.charge_id),
            "status": "paid" if str(data.get("status") or "").lower() == "approved" else "pending",
            "external_reference": request.charge_id,
            "qr_code": tx.get("qr_code") or "",
            "qr_code_base64": f"data:image/jpeg;base64,{tx.get('qr_code_base64')}" if tx.get("qr_code_base64") else "",
            "payment_url": tx.get("ticket_url") or "",
            "payload": {"payment": data},
        }

    async def handle_webhook(self, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        data = payload.get("data") or {}
        payment_id = data.get("id") or payload.get("id")
        if not payment_id:
            return None
        return {"provider_charge_id": str(payment_id), "status": "pending", "payload": {"webhook": payload}}


class PlaceholderProvider(PaymentProvider):
    def __init__(self, code: str, name: str, docs_url: str):
        self.code = code
        self.name = name
        self.docs_url = docs_url
        self.supported_methods = ["pix"]
        self.implemented = False
        self.config_fields = [
            {"name": "api_key", "label": "API Key / Token", "type": "password", "placeholder": "credencial"},
            {"name": "notes", "label": "Observacoes", "type": "textarea", "placeholder": "Campos finais entram na proxima rodada."},
        ]

    async def create_charge(self, config: dict[str, Any], request: ChargeRequest) -> dict[str, Any]:
        raise NotImplementedError("Provider cadastrado no painel, mas sem adapter final ainda.")


PROVIDERS: dict[str, PaymentProvider] = {
    "sandbox_pix": SandboxPixProvider(),
    "manual_pix": ManualPixProvider(),
    "asaas": AsaasProvider(),
    "efi_pix": EfiPixProvider(),
    "mercadopago_pix": MercadoPagoPixProvider(),
    "pagarme_pix": PlaceholderProvider("pagarme_pix", "Pagar.me PIX", "https://docs.pagar.me/"),
    "pagseguro_pix": PlaceholderProvider("pagseguro_pix", "PagBank / PagSeguro PIX", "https://developer.pagbank.com.br/"),
}


def provider_definitions() -> list[dict[str, Any]]:
    return [provider.metadata() for provider in PROVIDERS.values()]


def get_provider(code: str) -> PaymentProvider:
    if code not in PROVIDERS:
        raise KeyError(code)
    return PROVIDERS[code]


def _p12_base64_to_pem_pair(base64_value: str, password: str) -> tuple[str, str]:
    p12_bytes = base64.b64decode(base64_value)
    private_key, certificate, additional = pkcs12.load_key_and_certificates(
        p12_bytes,
        password.encode("utf-8") if password else None,
    )
    if private_key is None or certificate is None:
        raise ValueError("Nao foi possivel carregar o certificado P12.")
    cert_bundle = certificate.public_bytes(serialization.Encoding.PEM)
    for extra in additional or []:
        cert_bundle += extra.public_bytes(serialization.Encoding.PEM)
    key_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    Path(cert_file.name).write_bytes(cert_bundle)
    Path(key_file.name).write_bytes(key_bytes)
    return cert_file.name, key_file.name
