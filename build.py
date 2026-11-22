"""Monde Info : récupère les infos du jour (RSS, météo, crypto) et écrit news.json.
Pour ajouter un pays : copie le bloc FRANCE dans PAYS et change les flux et les villes."""
import json, re, html, urllib.request, datetime as dt
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

LM = "https://www.lemonde.fr/%s/rss_full.xml"
FRANCE = {
  "code": "FR", "name": "France",
  "cities": {"Paris": (48.85, 2.35), "Marseille": (43.30, 5.37), "Lyon": (45.76, 4.84),
             "Lille": (50.63, 3.06), "Toulouse": (43.60, 1.44), "Bordeaux": (44.84, -0.58),
             "Nantes": (47.22, -1.55), "Strasbourg": (48.58, 7.75), "Nice": (43.70, 7.26)},
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

def j(url):
    return json.loads(get(url))

def weather(p):
    out = []
    for city, (lat, lon) in p["cities"].items():
        try:
            u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                 "&current=temperature_2m,weather_code,wind_speed_10m"
                 "&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=5&timezone=auto" % (lat, lon))
            d = j(u)
            c, dl = d["current"], d["daily"]
            jours = [{"d": dl["time"][i], "max": round(dl["temperature_2m_max"][i]),
                      "min": round(dl["temperature_2m_min"][i]), "ciel": wmo(dl["weather_code"][i])}
                     for i in range(len(dl["time"]))]
            row = {"ville": city, "temp": round(c["temperature_2m"]), "ciel": wmo(c["weather_code"]),
                   "vent": round(c["wind_speed_10m"]), "jours": jours, "aqi": None}
            try:
                a = j("https://air-quality-api.open-meteo.com/v1/air-quality?latitude=%s&longitude=%s"
                      "&current=european_aqi&timezone=auto" % (lat, lon))
                row["aqi"] = a["current"]["european_aqi"]
            except Exception as e:
                print("Air ignoré :", city, e)
            out.append(row)
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

def safe(fn, default):
    try:
        return fn()
    except Exception as e:
        print("Source ignorée :", fn.__name__, e)
        return default

def rappels():
    u = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
         "rappelconso-v2-gtin-espaces/records?limit=30&order_by=date_publication%20desc")
    out = []
    for r in j(u).get("results", []):
        g = lambda *k: next((re.sub(r"\s+", " ", str(r[x])).strip() for x in k if r.get(x)), "")
        marque = g("marque_produit", "nom_de_la_marque_du_produit")
        modele = g("noms_des_modeles_ou_references", "modeles_ou_references", "nom_produit")
        titre = " – ".join(x for x in (marque, modele) if x) or g("sous_categorie_produit", "categorie_produit") or "Produit rappelé"
        out.append({"t": titre[:140], "cat": g("categorie_produit", "categorie_de_produit"),
                    "motif": g("motif_rappel", "motif_du_rappel")[:220],
                    "risque": g("risques_encourus", "risques_encourus_par_le_consommateur")[:220],
                    "u": g("lien_vers_la_fiche_rappel") or "https://rappel.conso.gouv.fr/",
                    "d": g("date_publication", "date_de_publication")})
    return out

def seismes():
    d = j("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
    out = []
    for f in d.get("features", []):
        p = f["properties"]
        out.append({"mag": p.get("mag"), "lieu": p.get("place") or "", "u": p.get("url") or "",
                    "d": dt.datetime.fromtimestamp(p["time"] / 1000, dt.timezone.utc).isoformat()})
    out.sort(key=lambda x: x["d"], reverse=True)
    return out[:20]

def electricite():
    u = ("https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
         "eco2mix-national-tr/records?limit=8&order_by=date_heure%20desc")
    for r in j(u).get("results", []):
        if r.get("consommation") is not None:
            v = lambda k: r.get(k) or 0
            return {"heure": r.get("date_heure"), "conso": v("consommation"), "co2": r.get("taux_co2"),
                    "mix": {"nucleaire": v("nucleaire"), "eolien": v("eolien"), "solaire": v("solaire"),
                            "hydro": v("hydraulique"), "gaz": v("gaz"),
                            "autres": v("charbon") + v("fioul") + v("bioenergies")}}
    return None

def change():
    sym = "USD,GBP,CHF,JPY,CAD,TRY,CNY"
    for base in ("https://api.frankfurter.dev/v1/latest", "https://api.frankfurter.app/latest"):
        try:
            d = j(base + "?base=EUR&symbols=" + sym)
            return {"date": d.get("date"), "rates": d["rates"]}
        except Exception as e:
            print("Change essai raté :", base, e)
    return None

def rivieres():
    out = []
    for nom, code in [("La Seine à Paris-Austerlitz", "F700000103")]:
        try:
            d = j("https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr?code_entite=%s"
                  "&grandeur_hydro=H&size=1&sort=desc&fields=date_obs,resultat_obs" % code)
            o = d["data"][0]
            out.append({"nom": nom, "niveau": round(o["resultat_obs"] / 1000, 2), "d": o["date_obs"]})
        except Exception as e:
            print("Rivière ignorée :", nom, e)
    return out

def wiki():
    d = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    u = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/fr.wikipedia/all-access/%d/%02d/%02d"
         % (d.year, d.month, d.day))
    out = []
    for a in j(u)["items"][0]["articles"]:
        t = a["article"]
        if ":" in t or t.startswith("Accueil") or t == "-":
            continue
        out.append({"t": t.replace("_", " "), "a": t, "v": a["views"]})
        if len(out) == 12:
            break
    return out

def sport():
    now = dt.datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    base = "https://www.thesportsdb.com/api/v1/json/3/"
    def ev(path):
        res = []
        for e in (j(base + path).get("events") or []):
            res.append({"h": e.get("strHomeTeam"), "a": e.get("strAwayTeam"),
                        "hs": e.get("intHomeScore"), "as": e.get("intAwayScore"), "d": e.get("dateEvent")})
        return res
    out = {"ligue": "Ligue 1", "passes": [], "prochains": [], "table": []}
    try: out["passes"] = ev("eventspastleague.php?id=4334")[::-1][:10]
    except Exception as e: print("Sport passés raté :", e)
    try: out["prochains"] = ev("eventsnextleague.php?id=4334")[:10]
    except Exception as e: print("Sport prochains raté :", e)
    try:
        for r in (j(base + "lookuptable.php?l=4334&s=%d-%d" % (y, y + 1)).get("table") or []):
            out["table"].append({"rang": r.get("intRank"), "eq": r.get("strTeam"), "j": r.get("intPlayed"),
                                 "pts": r.get("intPoints"), "diff": r.get("intGoalDifference")})
    except Exception as e: print("Classement raté :", e)
    return out


# Villes affichées sur le globe (les premières sont les plus importantes)
CITIES = [('Paris', 48.86, 2.35), ('New York', 40.71, -74.01), ('Londres', 51.51, -0.13), ('Tokyo', 35.68, 139.69), ('Moscou', 55.76, 37.62), ('Pékin', 39.9, 116.41), ('Delhi', 28.61, 77.21), ('Le Caire', 30.04, 31.24), ('São Paulo', -23.55, -46.63), ('Sydney', -33.87, 151.21), ('Los Angeles', 34.05, -118.24), ('Mexico', 19.43, -99.13), ('Lagos', 6.52, 3.38), ('Johannesburg', -26.2, 28.05), ('Dubaï', 25.2, 55.27), ('Berlin', 52.52, 13.4), ('Madrid', 40.42, -3.7), ('Rome', 41.9, 12.5), ('Istanbul', 41.01, 28.98), ('Bombay', 19.08, 72.88), ('Shanghai', 31.23, 121.47), ('Singapour', 1.35, 103.82), ('Séoul', 37.57, 126.98), ('Bangkok', 13.76, 100.5), ('Jakarta', -6.21, 106.85), ('Buenos Aires', -34.6, -58.38), ('Toronto', 43.65, -79.38), ('Washington', 38.91, -77.04), ('Nairobi', -1.29, 36.82), ('Riyad', 24.71, 46.68), ('Téhéran', 35.69, 51.39), ('Karachi', 24.86, 67.01), ('Dacca', 23.81, 90.41), ('Manille', 14.6, 120.98), ('Hong Kong', 22.32, 114.17), ('Le Cap', -33.92, 18.42), ('Casablanca', 33.57, -7.59), ('Lima', -12.05, -77.04), ('Bogota', 4.71, -74.07), ('Santiago', -33.45, -70.67), ('Kinshasa', -4.44, 15.27), ('Addis-Abeba', 9.03, 38.74), ('Kiev', 50.45, 30.52), ('Varsovie', 52.23, 21.01), ('Stockholm', 59.33, 18.07), ('Athènes', 37.98, 23.73), ('Lisbonne', 38.72, -9.14), ('Dublin', 53.35, -6.26), ('Oslo', 59.91, 10.75), ('Reykjavik', 64.15, -21.94), ('Anchorage', 61.22, -149.9), ('Honolulu', 21.31, -157.86), ('Auckland', -36.85, 174.76), ('Perth', -31.95, 115.86), ('Melbourne', -37.81, 144.96), ('Chicago', 41.88, -87.63), ('Houston', 29.76, -95.37), ('Miami', 25.76, -80.19), ('Vancouver', 49.28, -123.12), ('Montréal', 45.5, -73.57), ('La Havane', 23.11, -82.37), ('Caracas', 10.48, -66.9), ('Quito', -0.18, -78.47), ('La Paz', -16.5, -68.15), ('Montevideo', -34.9, -56.16), ('Rio de Janeiro', -22.91, -43.17), ('Brasília', -15.79, -47.88), ('Panama', 8.98, -79.52), ('Alger', 36.75, 3.06), ('Tunis', 36.81, 10.18), ('Tripoli', 32.89, 13.19), ('Dakar', 14.72, -17.47), ('Accra', 5.6, -0.19), ('Abidjan', 5.36, -4.01), ('Luanda', -8.84, 13.23), ('Dar es Salaam', -6.79, 39.21), ('Khartoum', 15.5, 32.56), ('Bagdad', 33.31, 44.36), ('Jérusalem', 31.77, 35.21), ('Kaboul', 34.53, 69.17), ('Tachkent', 41.3, 69.24), ('Almaty', 43.24, 76.89), ('Oulan-Bator', 47.89, 106.91), ('Katmandou', 27.72, 85.32), ('Colombo', 6.93, 79.86), ('Rangoun', 16.84, 96.17), ('Hanoï', 21.03, 105.85), ('Kuala Lumpur', 3.14, 101.69), ('Taipei', 25.03, 121.57), ('Wellington', -41.29, 174.78), ('Port Moresby', -9.44, 147.18), ('Nuuk', 64.18, -51.72), ('Vienne', 48.21, 16.37), ('Bruxelles', 50.85, 4.35), ('Amsterdam', 52.37, 4.9), ('Copenhague', 55.68, 12.57), ('Helsinki', 60.17, 24.94), ('Prague', 50.08, 14.44), ('Budapest', 47.5, 19.04), ('Bucarest', 44.43, 26.1), ('Marseille', 43.3, 5.37), ('Lyon', 45.76, 4.84), ('Lille', 50.63, 3.06), ('Toulouse', 43.6, 1.44), ('Bordeaux', 44.84, -0.58), ('Nantes', 47.22, -1.55), ('Strasbourg', 48.58, 7.75), ('Nice', 43.7, 7.26), ('Fort-de-France', 14.6, -61.07), ('Cayenne', 4.94, -52.33), ('Saint-Denis (La Réunion)', -20.88, 55.45), ('Nouméa', -22.27, 166.46), ('Papeete', -17.54, -149.57)]

def globe_temps():
    out = []
    for i in range(0, len(CITIES), 40):
        chunk = CITIES[i:i + 40]
        u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
             "&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto"
             % (",".join(str(c[1]) for c in chunk), ",".join(str(c[2]) for c in chunk)))
        d = j(u)
        if isinstance(d, dict):
            d = [d]
        for k, (c, r) in enumerate(zip(chunk, d)):
            cur = r.get("current") or {}
            if cur.get("temperature_2m") is None:
                continue
            out.append({"n": c[0], "lat": c[1], "lng": c[2], "t": round(cur["temperature_2m"]),
                        "c": wmo(cur.get("weather_code") or 0), "w": round(cur.get("wind_speed_10m") or 0), "p": i + k})
    return {"updated": dt.datetime.now(dt.timezone.utc).isoformat(), "cities": out}

if __name__ == "__main__":
    p = PAYS[0]
    data = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(), "country": p["name"],
            "items": news(p), "meteo": weather(p), "crypto": crypto(),
            "rappels": safe(rappels, []), "seismes": safe(seismes, []), "elec": safe(electricite, None),
            "change": safe(change, None), "rivieres": safe(rivieres, []), "wiki": safe(wiki, []),
            "sport": safe(sport, None), "globe": safe(globe_temps, None)}
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(len(data["items"]), "infos écrites")
