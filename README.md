# ESS – reprodukcia a porovnanie výsledkov

Bc. Adam Timko · Technická univerzita v Košiciach · Kyberbezpečnosť, 2. stupeň
adam.timko@student.tuke.sk

Balík obsahuje iba vstupné dáta, spúšťaný kód, referenčné numerické výsledky
a návod. Neobsahuje článok, revízne dokumenty, historické kópie, collector,
nepoužívané skripty, obrázky ani duplicitné protokoly predošlých behov.

## Spustenie

Rozbaľ ZIP a otvor terminál v priečinku s týmto README. Potrebuješ
Python 3.13 (testovaný 3.13.14), približne 2–3 GB voľného miesta a pamäť
na model s fixnými efektmi pre 269 791 riadkov. Výpočet trvá niekoľko minút.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe reproduce.py
```

Linux/macOS:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python reproduce.py
```

Internet je potrebný na inštaláciu závislostí. Samotná reprodukcia používa
zmrazené lokálne dáta, bez GitHub API alebo tokenov. Inštalácia do úplne nového
prostredia a ostatné operačné systémy neboli overené; testovaná je dostupná
Windows x64 inštalácia s pripnutými verziami.

## Čo sa overí

1. SHA-256 a veľkosť všetkých pribalených súborov.
2. Nové zostavenie CSV z databázy: všetkých 444 716 riadkov a 37 stĺpcov
   sa porovná so zmrazeným CSV, vrátane identifikátorov a chýbajúcich hodnôt.
3. Integrita datasetu pomocou pôvodného validátora.
4. Pôvodné analýzy RQ1/RQ3 a model RQ2 s klastrovaním podľa repozitára.
5. Prepočet deskriptívnych štatistík a výsledkov článku vrátane citlivostí RQ1,
   koeficientov/štandardných chýb/intervalov/R² RQ2 a korelácií RQ3.
6. Obojstranný Wilcoxonov test RQ3 na rovnakých 84 pároch repozitárov.
7. Opätovná SHA-256 kontrola vstupov, kódu a referencií po výpočte.

Po úspechu sa zobrazí **ALL CHECKS PASS**. Kontrol je 68.
`runs/LATEST.txt` obsahuje identifikátor posledného behu. V `runs/<id>/` nájdeš:

- `REPORT.md` – prehľad PASS/FAIL každej kontroly pre učiteľa;
- `report.json` – skutočné hodnoty, verzie, tolerancie a čas výpočtu;
- `logs/` – úplný výstup siedmich krokov, vrátane originálneho modelu RQ2;
- `canonical/verified_results/` – nové numerické výsledky článku a model RQ2;
- `paired/` – nový Wilcoxonov test a páry repozitárov;
- `project/results/` – nové výsledky pôvodných analýz;
- `project/data/analysis_prs.csv` – novo zostavený dataset.

Každý beh používa vlastný pracovný priečinok. Vstupy ani referenčné výsledky
neprepisuje. Pri nezhode skončí s FAIL a nenulovým návratovým kódom.
Nové logy a výsledky vzniknú pri spustení; staré sa v balíku neduplikujú.

## Referenčné výsledky na porovnanie

| Výsledok | Očakávaná hodnota |
|---|---:|
| Repozitáre / PR | 108 / 444 716 |
| RQ1 N / Spearman rho | 270 282 / 0.21256666527019186 |
| RQ1 strict N / rho | 220 972 / 0.15745691792471012 |
| RQ2 N / R² | 269 791 / 0.17692327062709656 |
| RQ2 beta veľkosť | 0.2480649033304534 |
| RQ2 beta skúsenosť | -0.1811141302083199 |
| RQ2 beta interakcia / p | 0.0017923462881492835 / 0.644808828794547 |
| RQ3 spoločné N | 243 463 |
| RQ3 rho review / merge | 0.21090305379332797 / 0.30119779991425955 |
| RQ3 silnejší merge vzťah | 77 z 84 repozitárov |
| RQ3 medián rozdielov | 0.07389449653123983 |
| Wilcoxon W / obojstranné p | 155 / 3.6098927900590186e-13 |

Identifikátory, počty a text sa porovnávajú presne. Reálne čísla majú relatívnu
aj absolútnu toleranciu `1e-10`; p-hodnoty relatívnu `1e-6` a absolútnu nulu.
Drobné rozdiely posledných desatinných miest medzi platformami sú možné.

## Obsah balíka

```text
README.md                  návod a očakávané výsledky
reproduce.py               jediný vstupný bod; 68 kontrol
requirements.txt           potrebné pripnuté numerické závislosti
MANIFEST.json              SHA-256 všetkých statických súborov
.gitattributes             LFS a zachovanie bajtov pri klonovaní
.gitignore                 vylúčené pracovné behy a prostredia
data/analysis_prs.csv      zmrazený dataset na porovnanie nového CSV
data/raw/study.sqlite3     zdrojová databáza vrátane histórie pre skúsenosť
scripts/original/          iba päť skutočne spúšťaných pôvodných skriptov
scripts/verify_results.py  numerická analýza článku
scripts/rq3_paired_test.py párový test RQ3
reference/original/        štyri špecifické tabuľky pôvodných analýz
reference/article/         šesť tabuliek článku a referenčný numerický audit
reference/rq3_paired_test.json  referenčný Wilcoxonov test
```

`reference/original/` overuje pôvodnú implementáciu; `reference/article/`
obsahuje výsledky skutočne použité v článku. Napríklad pôvodná deskriptívna
tabuľka zahŕňa aj záporné latencie; tabuľka článku používa správne analytické
vzorky. Špecifické tabuľky sú uložené osobitne. Tri bajtovo totožné tabuľky RQ1/RQ3
sú uložené iba raz v `reference/article/` a používajú ich obe porovnania.

Päť pôvodných skriptov zostalo nezmenených. Z numerickej analýzy článku boli
odstránené iba vytváranie obrázkov, archivovanie zdrojov a export pomocných
metadát; štatistické výpočty sa nemenili. Nové obrázky sa v tomto balíku netvoria.

## Známe diagnostické hlásenia

- Pôvodný validátor hlási chýbajúcu skúsenosť pri 491 PR v RQ1 bez identity
  autora. RQ2 ich vynecháva. Runner samostatne kontroluje presný počet aj
  záverečné PASS kritickej integrity.
- Dve záporné latencie sú uložené v dátach, ale nie sú analyticky eligible.
- Model RQ2 zachováva varovania o condition number a ranku kovariancie;
  nemení sa model ani klastrovaná inferencia.
- Wilcoxon je exploratívny obojstranný test rozdielov na úrovni repozitárov;
  deskriptívne poradie bolo známe pred jeho doplnením. Netestuje príčinnosť.

## GitLab/GitHub

Nahraj celý rozbalený obsah tohto balíka vrátane bodkových súborov.
Databáza a CSV potrebujú Git LFS; nastav ho pred prvým commitom:

```powershell
git init
git lfs install
git add .
git commit -m "Add ESS numerical reproduction package"
```

LFS pravidlá sú už v `.gitattributes`. Potom pripoj vlastný vzdialený repozitár
a odošli commit. `.venv/` a `runs/` sa necommitujú. Pri klonovaní stiahni
aj LFS dáta (`git lfs pull`). Odovzdanú verziu označ konkrétnym commitom/tagom.
Oficiálne informácie: [GitHub LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/configuring-git-large-file-storage),
[GitLab LFS](https://docs.gitlab.com/topics/git/lfs/).

Samostatná kontrola stiahnutých súborov nepotrebuje analytické balíky:

```powershell
python reproduce.py --verify-only
```
