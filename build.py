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

def page(title, body, root="", desc="Full Course Yellow — race weekends, camping at the track, and motorsport news by Darien Entwistle.", active=""):
    nav = "".join(f'<a href="{root}{h}" class="{"active" if active==k else ""}">{k}</a>'
                  for k, h in [("Home","index.html"),("Blog","blog.html"),("About","about.html")])
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<meta property="og:title" content="{esc(title)}"><meta property="og:image" content="{root}assets/img/sebring-hero.jpg">
<link rel="icon" href="{root}assets/img/flag.svg">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/style.css">
</head><body>
<div class="flagbar"></div>
<header class="site-header"><div class="wrap">
<a class="brand" href="{root}index.html"><img src="{root}assets/img/flag.svg" alt="" width="28" height="28"><span>FULL COURSE <b>YELLOW</b></span></a>
<button class="nav-toggle" aria-label="Menu" onclick="document.body.classList.toggle('nav-open')">☰</button>
<nav class="nav">{nav}<a href="{YT}" target="_blank" rel="noopener" class="yt">▶ YouTube</a></nav>
</div></header>
<main>{body}</main>
<footer class="site-footer"><div class="wrap">
<p><b>Full Course Yellow</b> · by Darien Entwistle · <a href="{YT}" target="_blank" rel="noopener">YouTube @djdarien93</a> · <a href="https://dentwistle.online" target="_blank" rel="noopener">dentwistle.online</a></p>
<p class="small">Photos &amp; original posts © Darien Entwistle, reused from <a href="https://dentwistle.online">dentwistle.online</a>. News headlines link to their original publishers.</p>
</div></footer>
</body></html>"""

def card(p, root=""):
    img = f'<img src="{root}{esc(p["image"])}" alt="{esc(p.get("image_alt",""))}" loading="lazy">' if p.get("image") else '<div class="card-noimg">🏁</div>'
    tag = '<span class="tag tag-ph">Starter</span>' if p["placeholder"] else ""
    return f"""<a class="card" href="{root}posts/{p['slug']}.html">{img}<div class="card-body">
<span class="tag">{esc(p['category'])}</span>{tag}<h3>{esc(p['title'])}</h3><p>{esc(p['excerpt'])}</p>
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
            if items: return {"provider": "NewsData.io", "items": items[:12]}
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
        return {"provider": "Motorsport.com RSS", "items": items[:12]}
    except Exception as e:
        print("RSS fallback failed:", type(e).__name__)
        return {"provider": None, "items": []}

def news_html(news):
    if not news["items"]:
        return '<p class="notice">Racing news is taking a pit stop — check back soon.</p>'
    out = []
    for n in news["items"]:
        img = f'<img src="{esc(n["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if n.get("image") else ""
        out.append(f'<a class="news-item" href="{esc(n["link"])}" target="_blank" rel="noopener">{img}<div><h4>{esc(n["title"])}</h4>'
                   f'<p>{esc(n.get("summary",""))}</p><span class="src">{esc(n.get("source") or "")}</span></div></a>')
    return "".join(out)

# ---------- build ----------
def build():
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    os.makedirs(os.path.join(OUT, "posts"))
    posts = load_posts()
    featured = next((p for p in posts if p["featured"]), posts[0])
    news = get_news()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%b %-d, %Y %H:%M UTC")
    json.dump({**news, "updated": stamp}, open(os.path.join(OUT, "news.json"), "w"), indent=1)

    others = [p for p in posts if p is not featured][:3]
    home = f"""
<section class="hero" style="background-image:linear-gradient(90deg,rgba(20,21,24,.95) 30%,rgba(20,21,24,.4)),url(assets/img/sebring-hero.jpg)">
<div class="wrap"><p class="kicker">Race weekends · Track camping · Motorsport news</p>
<h1>Life under the<br><span>yellow flag.</span></h1>
<p class="lead">Darien's notes from the grandstands and the campground — plus the latest racing headlines.</p>
<a class="btn" href="blog.html">Read the blog</a> <a class="btn btn-ghost" href="{YT}" target="_blank" rel="noopener">▶ Watch on YouTube</a></div></section>
<div class="wrap home-grid">
<section><h2 class="sec">Featured</h2>
<article class="featured"><a href="posts/{featured['slug']}.html"><img src="{esc(featured.get('image','assets/img/sebring-hero.jpg'))}" alt="{esc(featured.get('image_alt',''))}"></a>
<div class="featured-body"><span class="tag">{esc(featured['category'])}</span><h3><a href="posts/{featured['slug']}.html">{esc(featured['title'])}</a></h3>
<p>{esc(featured['excerpt'])}</p><a class="more" href="posts/{featured['slug']}.html">Read full post →</a></div></article>
<h2 class="sec">Latest posts</h2><div class="cards">{''.join(card(p) for p in others)}</div></section>
<aside class="news"><h2 class="sec">Racing News</h2><div class="news-list">{news_html(news)}</div>
<p class="small">Updated {stamp}{(' · via ' + esc(news['provider'])) if news['provider'] else ''}</p></aside>
</div>"""
    open(os.path.join(OUT, "index.html"), "w").write(page("Full Course Yellow — Motorsport Blog & Racing News", home, active="Home"))

    blog = f'<div class="wrap"><h1 class="page-title">The Blog</h1><p class="lead">Race reports, camping at the track, and the odd off-track story.</p><div class="cards cards-3">{"".join(card(p) for p in posts)}</div></div>'
    open(os.path.join(OUT, "blog.html"), "w").write(page("Blog — Full Course Yellow", blog, active="Blog"))

    for i, p in enumerate(posts):
        hero = f'<img class="post-hero" src="../{esc(p["image"])}" alt="{esc(p.get("image_alt",""))}">' if p.get("image") else ""
        nav = '<div class="post-nav">' + (f'<a href="{posts[i+1]["slug"]}.html">← {esc(posts[i+1]["title"])}</a>' if i+1 < len(posts) else "<span></span>") + \
              (f'<a href="{posts[i-1]["slug"]}.html">{esc(posts[i-1]["title"])} →</a>' if i > 0 else "") + "</div>"
        body = f"""<article class="wrap post"><a class="back" href="../blog.html">← All posts</a>
<span class="tag">{esc(p['category'])}</span><h1>{esc(p['title'])}</h1>
<p class="meta">{nice_date(p['date_obj'])} · Darien Entwistle</p>{hero}<div class="prose">{p['body']}</div>
<div class="yt-cta">🎥 More from the track on YouTube: <a href="{YT}" target="_blank" rel="noopener">@djdarien93</a></div>{nav}</article>"""
        open(os.path.join(OUT, "posts", p["slug"] + ".html"), "w").write(page(p["title"] + " — Full Course Yellow", body, root="../", desc=p["excerpt"], active="Blog"))

    about = open(os.path.join(ROOT, "src", "about.html"), encoding="utf-8").read().replace("{{YT}}", YT)
    open(os.path.join(OUT, "about.html"), "w").write(page("About — Full Course Yellow", about, active="About"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print(f"Built {len(posts)} posts; news: {news['provider']} ({len(news['items'])} items)")

if __name__ == "__main__":
    build()
