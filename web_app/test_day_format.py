import subprocess

base = "https://sentinel-s2-l2a.s3.amazonaws.com"
tests = {
    "June4_padded": "tiles/39/V/WC/2026/6/04/0/R10m/B04.jp2",
    "June4_unpadded": "tiles/39/V/WC/2026/6/4/0/R10m/B04.jp2",
    "June9_padded": "tiles/39/V/WC/2026/6/09/0/R10m/B04.jp2",
    "June9_unpadded": "tiles/39/V/WC/2026/6/9/0/R10m/B04.jp2",
}
for name, path in tests.items():
    url = f"{base}/{path}"
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "--connect-timeout", "10", "-m", "20", url], capture_output=True, text=True, timeout=30)
    print(f"{name}: HTTP {r.stdout.strip()}")
