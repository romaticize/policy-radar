import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Suppress only the single InsecureRequestWarning from urllib3
warnings.simplefilter('ignore', InsecureRequestWarning)

# The URL that is failing in your main script
test_url = 'https://www.rbi.org.in/notifications_rss.xml'

print(f"Attempting to connect to: {test_url}")

try:
    # Make the simplest possible request, with verification explicitly disabled
    response = requests.get(test_url, verify=False, timeout=30)

    # If the request succeeds, we print the status code
    print(f"✅ SUCCESS! Status Code: {response.status_code}")
    print("This means your network environment is likely the issue.")

except requests.exceptions.SSLError as e:
    # If it fails with the same SSL error, the problem is external
    print(f"❌ FAILED! The SSLError is still happening even in a minimal script.")
    print("This confirms the issue is your network proxy/firewall, not the scraper's code.")
    print(f"Error: {e}")

except Exception as e:
    print(f"An unexpected error occurred: {e}")
