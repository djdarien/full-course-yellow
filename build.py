#!/usr/bin/env python3
"""Static site builder for Full Course Yellow (stdlib only).

Usage: python3 build.py            -> builds into _site/
News: if NEWSDATA_API_KEY is set (GitHub Actions secret), racing news is fetched
from NewsData.io at build time (same API as Volt Report). Otherwise falls back
to the public Motorsport.com RSS feed. The key is never written to output.
"""
import os, re, json, shutil, html, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")
YT = "https://youtube.com/@djdarien93"
NEWS_QUERY = "motorsport OR IMSA OR NASCAR OR \"Formula 1\" OR IndyCar"
RSS_FALLBACK = "https://www.motorsport.com/rss/all/news/"

def esc(s): return html.escape(str(s), quote=True)

def load_posts():
    posts = []
    for fn in sorted(os.listdir(os.path.join(ROOT, "posts"))):
        if not fn.endswith(".html"): continue
        raw = open(os.path.join(ROOT, "posts", fn), encoding="utf-8").read()
        m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1); meta[k.strip()] = v.strip()
        meta["body"] = m.group(2)
        meta["slug"] = fn[:-5]
        meta["featured"] = meta.get("featured") == "true"
        meta["placeholder"] = meta.get("placeholder") == "true"
        meta["date_obj"] = datetime.date.fromisoformat(meta["date"])
        posts.append(meta)
    posts.sort(key=lambda p: p["date_obj"], reverse=True)
    return posts

def nice_date(d): return d.strftime("%B %-d, %Y")

SERIES = [  # (id, label, keywords) - first match wins
    ("f1", "F1", ["formula 1", "formula one", " f1 ", "f1 ", "grand prix", "verstappen", "hamilton", "leclerc", "norris", "piastri", "russell", "alonso", "red bull racing", "mclaren", "ferrari f1", "mercedes f1", "fia "]),
    ("imsa", "IMSA", ["imsa", "rolex 24", "daytona 24", "sebring", "petit le mans", "weathertech", "gtp", "gtd pro", "michelin pilot challenge"]),
    ("nascar", "NASCAR", ["nascar", "cup series", "xfinity", "truck series", "talladega", "martinsville", "bristol", "charlotte motor"]),
    ("indycar", "IndyCar", ["indycar", "indy 500", "indianapolis 500", "indy car", "palou", "o'ward", "newgarden"]),
]
NAV_SERIES = [("all", "Latest")] + [(s[0], s[1]) for s in SERIES] + [("other", "More")]

URL_HINTS = {"/f1/": "f1", "/formula-1": "f1", "/imsa/": "imsa",
             "/nascar": "nascar", "/indycar/": "indycar"}

def classify(text, link=""):
    l = (link or "").lower()
    for hint, sid in URL_HINTS.items():
        if hint in l: return sid, next(x[1] for x in SERIES if x[0] == sid)
    t = " " + (text or "").lower() + " "
    if any(h in l for h in ("/wec/", "/gtwc", "/le-mans/", "/elms/")) or any(k in t for k in (" wec ", "le mans", "gt world challenge", "gtwc", "hypercar")):
        return "other", "Sports Cars"
    for sid, label, kws in SERIES:
        if any(k in t for k in kws): return sid, label
    return "other", "Motorsport"

def picture(root, base, alt, sizes="100vw", eager=False, cls=""):
    """Responsive local image: base like 'assets/img/sebring-hero' with -480/-800/-1200 + full variants."""
    full = f"{root}{base}.jpg"
    srcset = ", ".join([f"{root}{base}-{w}.jpg {w}w" for w in (480, 800, 1200)] + [f"{full} 1800w"])
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    return f'<img class="{cls}" src="{root}{base}-800.jpg" srcset="{srcset}" sizes="{sizes}" alt="{esc(alt)}" {load} decoding="async">'

def post_img(p, root, sizes, eager=False, cls=""):
    img = p.get("image", "")
    if not img: return '<div class="noimg"><span>FCY</span></div>'
    base = img[:-4]
    if os.path.exists(os.path.join(ROOT, base + "-800.jpg")):
        return picture(root, base, p.get("image_alt", ""), sizes, eager, cls)
    return f'<img class="{cls}" src="{root}{esc(img)}" alt="{esc(p.get("image_alt",""))}" loading="lazy" decoding="async">'

def page(title, body, root="", desc="Full Course Yellow — race weekends, camping at the track, and motorsport news by Darien Entwistle.", active="", ticker=None):
    main_nav = "".join(f'<a href="{root}{h}" class="{"active" if active==k else ""}">{k}</a>'
                       for k, h in [("News","index.html"),("Blog","blog.html"),("About","about.html")])
    series_nav = "".join(f'<a href="{root}index.html#{sid}" data-series="{sid}">{lbl}</a>' for sid, lbl in NAV_SERIES)
    tick = ""
    if ticker:
        items = "".join(f'<a href="{esc(n["link"])}" target="_blank" rel="noopener"><b class="s-{n["sid"]}">{esc(n["slabel"])}</b>{esc(n["title"])}</a>' for n in ticker)
        tick = f'<div class="ticker" aria-label="Breaking news"><span class="ticker-label">Breaking</span><div class="ticker-track"><div class="ticker-move">{items}{items}</div></div></div>'
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><meta name="theme-color" content="#0d0e10">
<meta property="og:title" content="{esc(title)}"><meta property="og:image" content="{root}assets/img/sebring-hero-1200.jpg">
<link rel="icon" href="{root}assets/img/flag.svg">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,600;0,700;0,800;1,800;1,900&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/style.css">
</head><body>
<header class="masthead">
<div class="topbar"><div class="wrap">
<a class="brand" href="{root}index.html"><img src="{root}assets/img/flag.svg" alt="" width="30" height="30"><span>FULL COURSE <b>YELLOW</b></span></a>
<nav class="main-nav">{main_nav}<a href="{YT}" target="_blank" rel="noopener" class="yt">▶ YouTube</a></nav>
</div></div>
<nav class="series-nav" aria-label="Series"><div class="wrap">{series_nav}<a href="{root}blog.html" class="sn-blog">Race Weekends</a></div></nav>
</header>
{tick}
<main>{body}</main>
<footer class="site-footer"><div class="wrap foot-grid">
<div><a class="brand" href="{root}index.html"><img src="{root}assets/img/flag.svg" alt="" width="26" height="26"><span>FULL COURSE <b>YELLOW</b></span></a>
<p class="small">Race weekends, camping at the track, and motorsport news — by Darien Entwistle.</p></div>
<div><h4>Series</h4>{series_nav}</div>
<div><h4>Site</h4><a href="{root}blog.html">Blog</a><a href="{root}about.html">About</a><a href="{YT}" target="_blank" rel="noopener">YouTube @djdarien93</a><a href="https://dentwistle.online" target="_blank" rel="noopener">dentwistle.online</a></div>
</div><div class="wrap"><p class="small legal">Photos &amp; original posts © Darien Entwistle, reused from <a href="https://dentwistle.online">dentwistle.online</a>. Headlines link to and belong to their original publishers.</p></div></footer>
<script>
(function(){{var b=document.body,t=document.querySelector('.nav-open-btn');
function apply(){{var s=(location.hash||'#all').slice(1),grid=document.querySelector('[data-news-grid]');
document.querySelectorAll('.series-nav a[data-series]').forEach(function(a){{a.classList.toggle('active',a.dataset.series===s&&!!grid)}});
if(!grid)return;var n=0;grid.querySelectorAll('[data-sid]').forEach(function(c){{var show=s==='all'||c.dataset.sid===s;c.hidden=!show;if(show)n++}});
var e=document.querySelector('[data-empty]');if(e)e.hidden=n>0;var h=document.querySelector('[data-grid-title]');
if(h){{var a=document.querySelector('.series-nav a[data-series="'+s+'"]');h.textContent=(s==='all'?'Latest headlines':(a?a.textContent:s)+' news')}}}}
window.addEventListener('hashchange',function(){{apply();var g=document.getElementById('headlines');if(g&&location.hash)g.scrollIntoView({{behavior:'smooth'}})}});apply();}})();
</script>
</body></html>"""

def card(p, root=""):
    tag = '<span class="chip chip-ph">Starter</span>' if p["placeholder"] else ""
    return f"""<a class="card" href="{root}posts/{p['slug']}.html"><div class="card-media">{post_img(p, root, "(max-width:700px) 100vw, 380px")}</div><div class="card-body">
<span class="chip chip-blog">{esc(p['category'])}</span>{tag}<h3>{esc(p['title'])}</h3><p>{esc(p['excerpt'])}</p>
<time>{nice_date(p['date_obj'])}</time></div></a>"""

# ---------- news ----------
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FullCourseYellowBuilder/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r: return r.read()

def strip_tags(s): return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()

def get_news():
    key = os.environ.get("NEWSDATA_API_KEY", "").strip()
    if key:
        try:
            # Same endpoint/params pattern as Volt Report's script.js, but run server-side at build time.
            url = "https://newsdata.io/api/1/news?" + urllib.parse.urlencode(
                {"apikey": key, "q": NEWS_QUERY, "language": "en", "image": 1})
            data = json.loads(fetch(url))
            items = [{"title": a.get("title"), "link": a.get("link"), "image": a.get("image_url"),
                      "source": a.get("source_name") or a.get("source_id"), "date": a.get("pubDate"),
                      "summary": (a.get("description") or "")[:220]}
                     for a in data.get("results", []) if a.get("title") and a.get("link")]
            if items: return {"provider": "NewsData.io", "items": items[:24]}
        except Exception as e:
            print("NewsData fetch failed, falling back to RSS:", type(e).__name__)
    try:
        root = ET.fromstring(fetch(RSS_FALLBACK))
        items = []
        for it in root.iter("item"):
            enc = it.find("enclosure")
            items.append({"title": strip_tags(it.findtext("title")), "link": it.findtext("link"),
                          "image": enc.get("url") if enc is not None else None, "source": "Motorsport.com",
                          "date": it.findtext("pubDate"), "summary": strip_tags(it.findtext("description"))[:220]})
        return {"provider": "Motorsport.com RSS", "items": items[:24]}
    except Exception as e:
        print("RSS fallback failed:", type(e).__name__)
        return {"provider": None, "items": []}

def news_card(n, big=False):
    img = (f'<img src="{esc(n["image"])}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" width="400" height="225">'
           if n.get("image") else f'<div class="noimg s-bg-{n["sid"]}"><span>{esc(n["slabel"])}</span></div>')
    return (f'<a class="ncard" data-sid="{n["sid"]}" href="{esc(n["link"])}" target="_blank" rel="noopener"><div class="card-media">{img}'
            f'<span class="chip s-{n["sid"]}">{esc(n["slabel"])}</span></div><div class="card-body"><h3>{esc(n["title"])}</h3>'
            f'<p>{esc(n.get("summary",""))}</p><span class="src">{esc(n.get("source") or "")}</span></div></a>')

# ---------- build ----------
def build():
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    os.makedirs(os.path.join(OUT, "posts"))
    posts = load_posts()
    featured = next((p for p in posts if p["featured"]), posts[0])
    news = get_news()
    for n in news["items"]:
        n["sid"], n["slabel"] = classify(f'{n.get("title","")} {n.get("summary","")}', n.get("link",""))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%b %-d, %Y %H:%M UTC")
    json.dump({**news, "updated": stamp}, open(os.path.join(OUT, "news.json"), "w"), indent=1)
    items = news["items"]
    ticker = items[:10]

    # Lead story: top headline with an image; falls back to the featured blog post.
    lead = next((n for n in items if n.get("image")), None)
    if lead:
        lead_html = f"""<a class="lead" href="{esc(lead['link'])}" target="_blank" rel="noopener">
<img src="{esc(lead['image'])}" alt="" fetchpriority="high" decoding="async" referrerpolicy="no-referrer">
<div class="lead-txt"><span class="chip s-{lead['sid']}">{esc(lead['slabel'])}</span><span class="kicker">Lead story · {esc(lead.get('source') or '')}</span>
<h1>{esc(lead['title'])}</h1><p>{esc(lead.get('summary',''))}</p></div></a>"""
    else:
        lead_html = f"""<a class="lead" href="posts/{featured['slug']}.html">{post_img(featured, '', '100vw', True)}
<div class="lead-txt"><span class="chip chip-blog">{esc(featured['category'])}</span><h1>{esc(featured['title'])}</h1><p>{esc(featured['excerpt'])}</p></div></a>"""
    side = [n for n in items if n is not lead][:4]
    side_html = "".join(f'<a class="side-item" href="{esc(n["link"])}" target="_blank" rel="noopener"><span class="chip s-{n["sid"]}">{esc(n["slabel"])}</span><h4>{esc(n["title"])}</h4><span class="src">{esc(n.get("source") or "")}</span></a>' for n in side)
    grid_items = [n for n in items if n is not lead]
    others = [p for p in posts if p is not featured][:3]
    empty = '<p class="notice" data-empty hidden>No headlines for this series right now — check back after the next refresh.</p>'
    if not items:
        empty = '<p class="notice" data-empty>Racing news is taking a pit stop — check back soon.</p>'
    home = f"""
<section class="wrap lead-wrap">{lead_html}<aside class="side"><h2 class="sec">Top stories</h2>{side_html or '<p class="notice">No headlines yet.</p>'}</aside></section>
<section class="wrap fpost-wrap"><a class="fpost" href="posts/{featured['slug']}.html">
<div class="fpost-media">{post_img(featured, '', '(max-width:900px) 100vw, 640px')}</div>
<div class="fpost-txt"><span class="kicker">From the grandstands · Featured post</span><span class="chip chip-blog">{esc(featured['category'])}</span>
<h2>{esc(featured['title'])}</h2><p>{esc(featured['excerpt'])}</p><span class="more">Read the race weekend →</span></div></a></section>
<section class="wrap" id="headlines"><div class="sec-row"><h2 class="sec" data-grid-title>Latest headlines</h2><span class="small">Updated {stamp}{(' · via ' + esc(news['provider'])) if news['provider'] else ''}</span></div>
<div class="grid" data-news-grid>{''.join(news_card(n) for n in grid_items)}</div>{empty}</section>
<section class="wrap"><div class="sec-row"><h2 class="sec">Race weekends</h2><a class="more" href="blog.html">All posts →</a></div><div class="grid grid-3">{''.join(card(p) for p in others)}</div></section>
<section class="wrap yt-band"><div><span class="kicker">On YouTube</span><h2>Trackside video from Darien</h2><p>Race-weekend recaps from Daytona, Sebring and beyond.</p></div><a class="btn" href="{YT}" target="_blank" rel="noopener">▶ @djdarien93</a></section>"""
    open(os.path.join(OUT, "index.html"), "w").write(page("Full Course Yellow — Motorsport News & Race Weekends", home, active="News", ticker=ticker))

    blog = f'<div class="wrap"><header class="page-head"><span class="kicker">The blog</span><h1>Race Weekends</h1><p class="lead-p">Race reports, camping at the track, and the odd off-track story.</p></header><div class="grid grid-3 pb">{"".join(card(p) for p in posts)}</div></div>'
    open(os.path.join(OUT, "blog.html"), "w").write(page("Blog — Full Course Yellow", blog, active="Blog", ticker=ticker))

    for i, p in enumerate(posts):
        hero = f'<figure class="post-hero">{post_img(p, "../", "(max-width:900px) 100vw, 900px", True)}<figcaption>{esc(p.get("image_alt",""))}</figcaption></figure>' if p.get("image") else ""
        nav = '<div class="post-nav">' + (f'<a href="{posts[i+1]["slug"]}.html"><small>Previous</small>{esc(posts[i+1]["title"])}</a>' if i+1 < len(posts) else "<span></span>") + \
              (f'<a class="next" href="{posts[i-1]["slug"]}.html"><small>Next</small>{esc(posts[i-1]["title"])}</a>' if i > 0 else "") + "</div>"
        body = f"""<article class="post"><header class="wrap post-head"><a class="back" href="../blog.html">← Race Weekends</a>
<span class="chip chip-blog">{esc(p['category'])}</span>{'<span class="chip chip-ph">Starter</span>' if p['placeholder'] else ''}<h1>{esc(p['title'])}</h1>
<p class="meta">By <b>Darien Entwistle</b> · {nice_date(p['date_obj'])}</p></header><div class="wrap post-body">{hero}<div class="prose">{p['body']}</div>
<div class="yt-cta">🎥 More from the track on YouTube: <a href="{YT}" target="_blank" rel="noopener">@djdarien93</a></div>{nav}</div></article>"""
        open(os.path.join(OUT, "posts", p["slug"] + ".html"), "w").write(page(p["title"] + " — Full Course Yellow", body, root="../", desc=p["excerpt"], active="Blog"))

    about = open(os.path.join(ROOT, "src", "about.html"), encoding="utf-8").read().replace("{{YT}}", YT)
    open(os.path.join(OUT, "about.html"), "w").write(page("About — Full Course Yellow", about, active="About"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    counts = {}
    for n in items: counts[n["slabel"]] = counts.get(n["slabel"], 0) + 1
    print(f"Built {len(posts)} posts; news: {news['provider']} ({len(items)} items) {counts}")

if __name__ == "__main__":
    build()
