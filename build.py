"""Monde Info : récupère les infos du jour (RSS, météo, crypto) et écrit news.json.
Pour ajouter un pays : copie le bloc FRANCE dans PAYS et change les flux et les villes."""
import json, re, html, urllib.request, datetime as dt
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

LM = "https://www.lemonde.fr/%s/rss_full.xml"
FRANCE = {
  "code": "FR", "name": "France",
  "cities": {"Paris": (48.85, 2.35), "Marseille": (43.30, 5.37), "Lyon": (45.76, 4.84),
             "Lille": (50.63, 3.06), "Toulouse": (43.60, 1.44)},
  "feeds": [  # (url, catégorie par défaut, nom de la source)
    ("https://www.francetvinfo.fr/titres.rss", "une", "Franceinfo"),
    ("https://www.lemonde.fr/rss/une.xml", "une", "Le Monde"),
    ("https://www.lefigaro.fr/rss/figaro_actualites-a-la-une.xml", "une", "Le Figaro"),
    ("https://www.20minutes.fr/feeds/rss-une.xml", "une", "20 Minutes"),
    (LM % "politique", "polit", "Le Monde"),
    (LM % "economie", "eco", "Le Monde"),
    (LM % "international", "inter", "Le Monde"),
    (LM % "sante", "sante", "Le Monde"),
    (LM % "planete", "envi", "Le Monde"),
    (LM % "sciences", "tech", "Le Monde"),
    (LM % "societe", "societ", "Le Monde"),
    (LM % "education", "educ", "Le Monde"),
    (LM % "culture", "culture", "Le Monde"),
    (LM % "sport", "sport", "Le Monde"),
    ("https://www.lequipe.fr/rss/actu_rss.xml", "sport", "L'Équipe"),
  ],
}
PAYS = [FRANCE]

# Mots-clés : le premier qui correspond décide de la catégorie (sinon catégorie du flux)
RULES = [
  ("crypto", ["bitcoin", "ethereum", "crypto"]),
  ("accid", ["accident", "collision", "carambolage", "déraill", "crash", "percuté"]),
  ("catas", ["inondation", "séisme", "tremblement de terre", "tempête", "incendie", "ouragan", "tsunami", "éruption", "avalanche", "crue", "glissement de terrain"]),
  ("meteo", ["météo", "vigilance orange", "vigilance rouge", "canicule", "orages", "neige", "verglas"]),
  ("medic", ["médicament", "cancer", "essai clinique", "chirurg", "greffe", "traitement contre"]),
  ("sante", ["épidémie", "grippe", "covid", "hôpital", "vaccin", "virus", "santé", "urgences"]),
  ("elec", ["présidentielle", "candidat à", "candidate à", "sondage"]),
  ("pres", ["macron", "élysée", "chef de l'état", "chef de l’état"]),
  ("crise", ["récession", "faillite", "inflation", "krach", "dette", "défaut de paiement", "crise économique"]),
  ("bourse", ["cac 40", "bourse", "wall street", "euro face au dollar"]),
  ("energie", ["électricité", "nucléaire", "carburant", "edf", "énergie", "pétrole"]),
  ("trans", ["sncf", "grève", "ratp", "trafic aérien", "aéroport", "train", "tgv"]),
  ("secu", ["terroris", "attentat", "armée", "défense", "militaire"]),
  ("faits", ["tribunal", "procès", "garde à vue", "meurtre", "interpellé", "mis en examen", "cambriolage"]),
]
MAX_PER_CAT = 40

def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "MondeInfoBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def to_date(s):
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        except Exception:
            return dt.datetime.now(dt.timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)

def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ns = "{http://www.w3.org/2005/Atom}"
    out = []
    for it in root.iter("item"):
        out.append((clean(it.findtext("title")), (it.findtext("link") or "").strip(),
                    it.findtext("pubDate"), clean(it.findtext("description"))))
    for it in root.iter(ns + "entry"):
        l = it.find(ns + "link")
        out.append((clean(it.findtext(ns + "title")), (l.get("href") if l is not None else ""),
                    it.findtext(ns + "updated") or it.findtext(ns + "published"), clean(it.findtext(ns + "summary"))))
    return out

def categorize(text, default):
    t = text.lower()
    for cat, words in RULES:
        if any(w in t for w in words):
            return cat
    return default

WMO = [(0, "Dégagé"), (3, "Nuageux"), (48, "Brouillard"), (57, "Bruine"), (67, "Pluie"),
       (77, "Neige"), (82, "Averses"), (86, "Averses de neige"), (99, "Orage")]
def wmo(code):
    for m, label in WMO:
        if code <= m:
            return label
    return "Variable"

def news(p):
    items, seen = [], set()
    for url, default, src in p["feeds"]:
        try:
            for title, link, date, desc in parse(get(url)):
                if not title or not link.startswith("http") or link in seen:
                    continue
                seen.add(link)
                items.append({"t": title, "s": src, "u": link, "d": to_date(date).isoformat(),
                              "c": categorize(title + " " + desc, default)})
        except Exception as e:
            print("Flux ignoré :", url, e)
    items.sort(key=lambda x: x["d"], reverse=True)
    count, kept = {}, []
    for i in items:
        count[i["c"]] = count.get(i["c"], 0) + 1
        if count[i["c"]] <= MAX_PER_CAT:
            kept.append(i)
    return kept

def weather(p):
    out = []
    for city, (lat, lon) in p["cities"].items():
        try:
            u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                 "&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto" % (lat, lon))
            c = json.loads(get(u))["current"]
            out.append({"ville": city, "temp": round(c["temperature_2m"]), "ciel": wmo(c["weather_code"]),
                        "vent": round(c["wind_speed_10m"])})
        except Exception as e:
            print("Météo ignorée :", city, e)
    return out

def crypto():
    try:
        u = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana"
             "&vs_currencies=eur&include_24hr_change=true")
        d = json.loads(get(u))
        names = {"bitcoin": "Bitcoin", "ethereum": "Ethereum", "solana": "Solana"}
        return [{"nom": names[k], "eur": v["eur"], "var": round(v.get("eur_24h_change", 0), 1)} for k, v in d.items()]
    except Exception as e:
        print("Crypto ignorée :", e)
        return []

if __name__ == "__main__":
    p = PAYS[0]
    data = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(), "country": p["name"],
            "items": news(p), "meteo": weather(p), "crypto": crypto()}
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(len(data["items"]), "infos écrites")
