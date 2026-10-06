import re, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
path = sys.argv[1]
h = open(path, encoding='utf-8', errors='replace').read()
items = re.findall(r'<li class="b_algo".*?</li>', h, re.S)
print('results:', len(items))
for it in items[:10]:
    m = re.search(r'<h2>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', it, re.S)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(2))
        print('-', title.strip()[:90])
        print('  ', m.group(1)[:120])
    else:
        t = re.sub(r'<[^>]+>', ' ', it)
        t = re.sub(r'\s+', ' ', t).strip()
        print('-', t[:120])
