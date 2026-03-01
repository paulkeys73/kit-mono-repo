import sys
import whois
import socket
import dns.resolver  # 📦 pip install dnspython

def check_domain_availability(domain):
    try:
        print(f"[*] Looking up WHOIS info for: {domain}")
        domain_info = whois.whois(domain)

        if not domain_info.domain_name:
            print(f"[❌] Domain '{domain}' is NOT registered.")
            return

        # 📛 Basic WHOIS Details
        registrar = domain_info.registrar or "Unknown"
        creation_date = domain_info.creation_date or "Unknown"
        expiration_date = domain_info.expiration_date or "Unknown"

        print(f"\n[✅] Domain '{domain}' is registered.")
        print(f"📛 Registrar       : {registrar}")
        print(f"📆 Created on      : {creation_date}")
        print(f"⏳ Expires on      : {expiration_date}")

        # 🛡️ Privacy Check
        registrant_name = getattr(domain_info, "name", None)
        registrant_org = getattr(domain_info, "org", None)
        if registrant_name and ("privacy" in registrant_name.lower() or "private" in registrant_name.lower()):
            print("🛡️ Privacy         : WHOIS Privacy Protection enabled (Name field)")
        elif registrant_org and ("privacy" in registrant_org.lower() or "private" in registrant_org.lower()):
            print("🛡️ Privacy         : WHOIS Privacy Protection enabled (Org field)")
        else:
            print("🛡️ Privacy         : Likely NOT using WHOIS Privacy")

        # 🌐 DNS Records Check
        print(f"\n🌐 DNS Records Check for '{domain}':")
        try:
            a_records = dns.resolver.resolve(domain, 'A')
            print("   A Record(s)     :", ", ".join([r.address for r in a_records]))
        except:
            print("   A Record(s)     : Not found")

        try:
            ns_records = dns.resolver.resolve(domain, 'NS')
            print("   NS Record(s)    :", ", ".join([r.to_text() for r in ns_records]))
        except:
            print("   NS Record(s)    : Not found")

        try:
            cname_records = dns.resolver.resolve(domain, 'CNAME')
            print("   CNAME Record(s) :", ", ".join([r.to_text() for r in cname_records]))
        except:
            print("   CNAME Record(s) : Not found")

    except whois.parser.PywhoisError:
        print(f"[❌] Domain '{domain}' is NOT registered.")
    except socket.gaierror:
        print(f"[⚠️] Network error: Could not resolve '{domain}'")
    except Exception as e:
        print(f"[!] Unexpected error occurred: {e}")

def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <domain>")
        sys.exit(1)

    domain = sys.argv[1]
    check_domain_availability(domain)

if __name__ == "__main__":
    main()
