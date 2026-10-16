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
NEWS_QUERY = "Formula 1 OR IMSA OR NASCAR OR IndyCar OR \"Indy 500\" OR WeatherTech OR \"Le Mans\" OR motorsport"
RSS_FALLBACK = "https://www.motorsport.com/rss/all/news/"
# Per-series public feeds so every series filter has headlines even on quiet days.
RSS_SERIES = {"f1": "https://www.motorsport.com/rss/f1/news/", "imsa": "https://www.motorsport.com/rss/imsa/news/",
              "nascar": "https://www.motorsport.com/rss/nascar-cup/news/", "indycar": "https://www.motorsport.com/rss/indycar/news/"}
PER_SERIES = 6

def esc(s): return html.escape(str(s), quote=True)

POSTS_DIR = os.path.join(ROOT, "content", "posts")

def yaml_scalar(v):
    v = v.strip()
    if v[:1] == '"' and v[-1:] == '"':
        try: return json.loads(v)
        except Exception: return v[1:-1]
    if v[:1] == "'" and v[-1:] == "'": return v[1:-1].replace("''", "'")
    if v.lower() in ("true", "yes"): return True
    if v.lower() in ("false", "no"): return False
    if v.lower() in ("null", "~", ""): return ""
    return v

def parse_front_matter(text):
    """Minimal YAML subset (what Pages CMS writes): key: scalar, quoted strings, booleans, | and > blocks."""
    meta, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*):\s?(.*)$", lines[i]); i += 1
        if not m: continue
        k, v = m.group(1), m.group(2)
        if v.strip()[:1] in ("|", ">"):
            block = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip()); i += 1
            meta[k] = ("\n" if v.strip()[0] == "|" else " ").join(block).strip()
        else:
            # plain multi-line continuation
            while i < len(lines) and lines[i].startswith("  ") and not re.match(r"^[A-Za-z_][\w-]*:", lines[i]):
                v += " " + lines[i].strip(); i += 1
            meta[k] = yaml_scalar(v)
    return meta

def md_inline(t):
    t = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)", r'<img src="\2" alt="\1" loading="lazy">', t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)\*(?!\w)|(?<!\w)_(?!\s)(.+?)_(?!\w)", lambda m: f"<em>{m.group(1) or m.group(2)}</em>", t)

def markdown_to_html(src):
    """Small Markdown renderer for bodies written in the CMS source/markdown mode. HTML bodies pass through."""
    if re.search(r"^\s*<(p|h\d|ul|ol|div|figure|blockquote|iframe|img|table)\b", src, re.M | re.I): return src
    out, para, lst = [], [], None
    def flush():
        nonlocal lst
        if para: out.append("<p>" + md_inline(" ".join(para)) + "</p>"); para.clear()
        if lst: out.append(f"</{lst}>"); lst = None
    for line in src.splitlines():
        l = line.rstrip()
        h = re.match(r"^(#{1,6})\s+(.*)", l); ul = re.match(r"^\s*[-*+]\s+(.*)", l); ol = re.match(r"^\s*\d+[.)]\s+(.*)", l)
        if not l.strip(): flush()
        elif h:
            flush(); n = max(2, min(len(h.group(1)) + 1, 4)); out.append(f"<h{n}>{md_inline(h.group(2))}</h{n}>")
        elif ul or ol:
            kind = "ul" if ul else "ol"
            if para: out.append("<p>" + md_inline(" ".join(para)) + "</p>"); para.clear()
            if lst != kind:
                if lst: out.append(f"</{lst}>")
                out.append(f"<{kind}>"); lst = kind
            out.append(f"<li>{md_inline((ul or ol).group(1))}</li>")
        elif l.startswith(">"): flush(); out.append(f"<blockquote><p>{md_inline(l.lstrip('> '))}</p></blockquote>")
        else: para.append(l.strip())
    flush()
    return "\n".join(out)

def youtube_embed(url):
    m = re.search(r"(?:youtu\.be/|v=|/embed/|/shorts/|/live/)([\w-]{11})", url or "")
    if not m: return ""
    return (f'<div class="video"><iframe src="https://www.youtube.com/embed/{m.group(1)}" title="YouTube video" loading="lazy" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>')

def site_path(p):
    """CMS writes media paths as /assets/img/...; the site lives under /full-course-yellow/, so make them relative."""
    p = (p or "").strip()
    return p[1:] if p.startswith("/assets/") else p

def load_posts():
    posts = []
    for fn in sorted(os.listdir(POSTS_DIR)):
        if not fn.endswith(".md"): continue
        raw = open(os.path.join(POSTS_DIR, fn), encoding="utf-8").read().lstrip("\ufeff")
        m = re.match(r"---\s*\n(.*?)\n---\s*\n?(.*)", raw, re.S)
        if not m:
            print("Skipping (no front matter):", fn); continue
        meta = parse_front_matter(m.group(1))
        if meta.get("draft") is True: continue
        if not meta.get("title"):
            print("Skipping (no title):", fn); continue
        slug = re.sub(r"[^a-z0-9-]+", "-", fn[:-3].lower()).strip("-")
        try: d = datetime.date.fromisoformat(str(meta.get("date", ""))[:10])
        except ValueError:
            mm = re.match(r"(\d{4})-(\d{2})-(\d{2})", fn); d = datetime.date(*map(int, mm.groups())) if mm else datetime.date.today()
        body = markdown_to_html(m.group(2).strip())
        yt = youtube_embed(meta.get("youtube"))
        if re.search(r"(<p>\s*)?\{\{\s*youtube\s*\}\}(\s*</p>)?", body):
            body = re.sub(r"(<p>\s*)?\{\{\s*youtube\s*\}\}(\s*</p>)?", lambda _m: yt, body)
        elif yt:
            body = yt + body
        if meta.get("placeholder_note") or meta.get("placeholder") is True:
            note = meta.get("placeholder_note") or "Starter / placeholder post. Darien, edit or replace this with your own words."
            body = f'<p class="placeholder-note">📝 {note}</p>\n' + body
        if meta.get("source_url"):
            body = (f'<p class="source-note">Originally published on <a href="{esc(meta["source_url"])}">dentwistle.online</a> by Darien Entwistle.</p>\n') + body
        body = re.sub(r'(src|href)="/assets/', r'\1="../assets/', body)
        posts.append({**meta, "title": str(meta["title"]), "slug": slug, "body": body, "date_obj": d,
                      "category": str(meta.get("category") or "Racing"), "excerpt": str(meta.get("excerpt") or ""),
                      "image": site_path(meta.get("image")), "image_alt": str(meta.get("image_alt") or ""),
                      "featured": meta.get("featured") is True, "placeholder": meta.get("placeholder") is True})
    posts.sort(key=lambda p: (p["date_obj"], p["slug"]), reverse=True)
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
                       for k, h in [("News","index.html"),("Blog","blog.html"),("Series","series.html"),("About","about.html")])
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
<div><h4>Site</h4><a href="{root}blog.html">Blog</a><a href="{root}series.html">Series guide</a><a href="{root}about.html">About</a><a href="{YT}" target="_blank" rel="noopener">YouTube @djdarien93</a><a href="https://dentwistle.online" target="_blank" rel="noopener">dentwistle.online</a></div>
</div><div class="wrap"><p class="small legal">Photos &amp; original posts © Darien Entwistle, reused from <a href="https://dentwistle.online">dentwistle.online</a>. Headlines link to and belong to their original publishers.</p></div></footer>
<script>
(function(){{var b=document.body,t=document.querySelector('.nav-open-btn');
function apply(){{var s=(location.hash||'#all').slice(1),grid=document.querySelector('[data-news-grid]');
document.querySelectorAll('.series-nav a[data-series]').forEach(function(a){{a.classList.toggle('active',a.dataset.series===s&&!!grid)}});
if(!grid)return;var n=0;grid.querySelectorAll('[data-sid]').forEach(function(c){{var show=s==='all'||c.dataset.sid===s;c.hidden=!show;if(show)n++}});
var e=document.querySelector('[data-empty]');if(e){{e.hidden=n>0;var L=document.querySelector('[data-empty-links]'),R=window.FCY_RELATED||{{}};if(L&&!n){{var r=(R[s]||R.all||[]);L.innerHTML='<a class="btn btn-sm" href="series.html#'+s+'">Series guide →</a>'+r.map(function(p){{return '<a class="rel" href="'+p.u+'">From the blog: '+p.t.replace(/</g,'&lt;')+'</a>'}}).join('')}}}}var h=document.querySelector('[data-grid-title]');
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
    items = rss_items(RSS_FALLBACK)[:18]
    for sid, url in RSS_SERIES.items():
        items += [dict(it, sid_hint=sid) for it in rss_items(url)[:PER_SERIES]]
    seen, out = set(), []
    for it in items:
        k = (it["link"] or "").split("?")[0]
        if k and k not in seen: seen.add(k); out.append(it)
    out.sort(key=lambda it: it.get("ts") or 0, reverse=True)
    return {"provider": "Motorsport.com RSS" if out else None, "items": out}

def rss_items(url):
    from email.utils import parsedate_to_datetime
    try:
        root = ET.fromstring(fetch(url))
    except Exception as e:
        print("RSS fetch failed:", url, type(e).__name__); return []
    items = []
    for it in root.iter("item"):
        enc = it.find("enclosure")
        try: ts = parsedate_to_datetime(it.findtext("pubDate")).timestamp()
        except Exception: ts = 0
        items.append({"title": strip_tags(it.findtext("title")), "link": it.findtext("link"),
                      "image": enc.get("url") if enc is not None else None, "source": "Motorsport.com",
                      "date": it.findtext("pubDate"), "ts": ts, "summary": strip_tags(it.findtext("description"))[:220]})
    return items

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
    featured = next((p for p in posts if p["featured"]), posts[0] if posts else None)
    news = get_news()
    for n in news["items"]:
        n["sid"], n["slabel"] = (n["sid_hint"], dict((x[0], x[1]) for x in SERIES)[n["sid_hint"]]) if n.get("sid_hint") else classify(f'{n.get("title","")} {n.get("summary","")}', n.get("link",""))
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
    empty = '<div class="empty" data-empty hidden><h3>Quiet on track right now</h3><p>No fresh headlines for this series at the last refresh — news updates every 3 hours.</p><div class="empty-links" data-empty-links></div></div>'
    related = {"imsa": [p for p in posts if "Racing" in p["category"]], "all": posts[:2]}
    rel_json = json.dumps({k: [{"t": p["title"], "u": f"posts/{p['slug']}.html"} for p in v] for k, v in related.items()})
    empty += f'<script>window.FCY_RELATED={rel_json};</script>'
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

    blog = f'<div class="wrap"><header class="page-head"><span class="kicker">The blog</span><h1>Race Weekends</h1><p class="lead-p">Race reports, camping at the track, and notes from the grandstands.</p></header><div class="grid grid-3 pb">{"".join(card(p) for p in posts)}</div></div>'
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

    series = open(os.path.join(ROOT, "src", "series.html"), encoding="utf-8").read()
    open(os.path.join(OUT, "series.html"), "w").write(page("Series Guide — Full Course Yellow", series, active="Series",
         desc="A plain-English guide to F1, IMSA, NASCAR and IndyCar."))
    about = open(os.path.join(ROOT, "src", "about.html"), encoding="utf-8").read().replace("{{YT}}", YT)
    open(os.path.join(OUT, "about.html"), "w").write(page("About — Full Course Yellow", about, active="About"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    counts = {}
    for n in items: counts[n["slabel"]] = counts.get(n["slabel"], 0) + 1
    print(f"Built {len(posts)} posts; news: {news['provider']} ({len(items)} items) {counts}")

if __name__ == "__main__":
    build()
