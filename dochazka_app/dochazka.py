
import csv
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.align import Align

console = Console()

FORMAT_CASU = "%Y-%m-%d %H:%M"
KRATKA_SMENA = 5.0
DLOUHA_SMENA = 10.0


def nacti_data(cesta):
    """Načte a zkontroluje záznamy z CSV."""
    zaznamy = []
    chyby = []

    try:
        with open(cesta, "r", encoding="utf-8-sig", newline="") as soubor:
            ctenar = csv.DictReader(soubor, delimiter=";")

            povinne_sloupce = {
                "číslo čipu", "zaměstnanec", "příchod", "odchod"
            }

            if not ctenar.fieldnames:
                raise ValueError("CSV soubor neobsahuje záhlaví.")

            ctenar.fieldnames = [
                nazev.strip() for nazev in ctenar.fieldnames
            ]

            chybejici = povinne_sloupce - set(ctenar.fieldnames)
            if chybejici:
                raise ValueError(
                    "Chybějící sloupce: " + ", ".join(sorted(chybejici))
                )

            for cislo_radku, radek in enumerate(ctenar, start=2):
                try:
                    zaznam = {
                        k.strip(): (v.strip() if v else "")
                        for k, v in radek.items()
                        if k is not None
                    }

                    cip = zaznam["číslo čipu"]
                    jmeno = zaznam["zaměstnanec"]

                    if not cip or not jmeno:
                        raise ValueError("Chybí číslo čipu nebo jméno.")

                    prichod = datetime.strptime(
                        zaznam["příchod"], FORMAT_CASU
                    )
                    odchod = datetime.strptime(
                        zaznam["odchod"], FORMAT_CASU
                    )

                    if odchod <= prichod:
                        raise ValueError(
                            "Odchod musí být později než příchod."
                        )

                    zaznam["_prichod"] = prichod
                    zaznam["_odchod"] = odchod
                    zaznam["_hodiny"] = (
                        odchod - prichod
                    ).total_seconds() / 3600

                    zaznamy.append(zaznam)

                except (ValueError, KeyError) as chyba:
                    chyby.append(
                        f"Řádek {cislo_radku}: {chyba}"
                    )

    except FileNotFoundError:
        raise ValueError(f"Soubor '{cesta}' nebyl nalezen.")
    except PermissionError:
        raise ValueError(f"Nemám oprávnění číst soubor '{cesta}'.")
    except OSError as chyba:
        raise ValueError(f"Soubor nelze načíst: {chyba}")

    if not zaznamy:
        podrobnosti = "\n".join(chyby[:5])
        raise ValueError(
            "V CSV nejsou žádné platné záznamy.\n" + podrobnosti
        )

    return zaznamy, chyby


def vypocitej_statistiky(zaznamy):
    """Sečte směny jednotlivých zaměstnanců."""
    zamestnanci = {}

    for z in zaznamy:
        cip = z["číslo čipu"]

        if cip not in zamestnanci:
            zamestnanci[cip] = {
                "číslo čipu": cip,
                "zaměstnanec": z["zaměstnanec"],
                "počet_směn": 0,
                "celkem_hodin": 0.0,
                "směny": []
            }

        osoba = zamestnanci[cip]
        osoba["počet_směn"] += 1
        osoba["celkem_hodin"] += z["_hodiny"]

        osoba["směny"].append({
            "datum": z["_prichod"].strftime("%Y-%m-%d"),
            "příchod": z["_prichod"].strftime(FORMAT_CASU),
            "odchod": z["_odchod"].strftime(FORMAT_CASU),
            "hodiny": round(z["_hodiny"], 2)
        })

    vysledky = []

    for osoba in zamestnanci.values():
        pocet = osoba["počet_směn"]
        celkem = osoba["celkem_hodin"]

        vysledky.append({
            "číslo čipu": osoba["číslo čipu"],
            "zaměstnanec": osoba["zaměstnanec"],
            "počet_směn": pocet,
            "celkem_hodin": round(celkem, 2),
            "průměrná_směna": round(celkem / pocet, 2),
            "směny": osoba["směny"]
        })

    return sorted(
        vysledky,
        key=lambda osoba: osoba["zaměstnanec"].casefold()
    )


def denni_statistiky(zaznamy):
    """Najde první příchod, poslední odchod a směny za každý den."""
    dny = defaultdict(list)

    for z in zaznamy:
        datum = z["_prichod"].date().isoformat()
        dny[datum].append(z)

    vysledky = []

    for datum, smeny in sorted(dny.items()):
        prvni = min(smeny, key=lambda z: z["_prichod"])
        posledni = max(smeny, key=lambda z: z["_odchod"])

        vysledky.append({
            "datum": datum,
            "počet_směn": len(smeny),
            "první_příchod": prvni["zaměstnanec"],
            "čas_prvního_příchodu":
                prvni["_prichod"].strftime("%H:%M"),
            "poslední_odchod": posledni["zaměstnanec"],
            "čas_posledního_odchodu":
                posledni["_odchod"].strftime("%H:%M"),
            "průměrná_délka_směny": round(
                sum(z["_hodiny"] for z in smeny) / len(smeny), 2
            )
        })

    return vysledky


def najdi_anomalie(zaznamy):
    """Označí neobvykle krátké a dlouhé směny."""
    anomalie = []

    for z in zaznamy:
        hodiny = z["_hodiny"]
        duvod = None

        if hodiny < KRATKA_SMENA:
            duvod = "Krátká směna"
        elif hodiny > DLOUHA_SMENA:
            duvod = "Dlouhá směna"

        if duvod:
            anomalie.append({
                "zaměstnanec": z["zaměstnanec"],
                "číslo čipu": z["číslo čipu"],
                "datum": z["_prichod"].strftime("%Y-%m-%d"),
                "příchod": z["_prichod"].strftime("%H:%M"),
                "odchod": z["_odchod"].strftime("%H:%M"),
                "hodiny": round(hodiny, 2),
                "důvod": duvod
            })

    return anomalie



def zobraz_prehled(zamestnanci):
    console.clear()

    celkem_hodin = sum(
        z["celkem_hodin"] for z in zamestnanci
    )

    tabulka = Table(
        title="📊  PŘEHLED ZAMĚSTNANCŮ",
        caption="Souhrnná analýza evidovaných směn",
        box=box.ROUNDED,
        border_style="bright_cyan",
        header_style="bold bright_cyan",
        show_lines=True,
        expand=True
    )

    tabulka.add_column("ZAMĚSTNANEC", style="bold white")
    tabulka.add_column("ČÍSLO ČIPU", justify="center")
    tabulka.add_column("SMĚNY", justify="right")
    tabulka.add_column("CELKEM HODIN", justify="right",
                       style="bright_green")
    tabulka.add_column("PRŮMĚR / SMĚNA", justify="right",
                       style="bright_yellow")

    for z in sorted(
        zamestnanci,
        key=lambda osoba: osoba["celkem_hodin"],
        reverse=True
    ):
        tabulka.add_row(
            z["zaměstnanec"],
            z["číslo čipu"],
            str(z["počet_směn"]),
            f"{z['celkem_hodin']:.2f} h",
            f"{z['průměrná_směna']:.2f} h"
        )

    console.print()
    console.print(tabulka)

    souhrn = Table(box=box.SIMPLE, expand=True)
    souhrn.add_column("UKAZATEL", style="dim")
    souhrn.add_column("HODNOTA", justify="right",
                      style="bold bright_cyan")

    souhrn.add_row("Počet zaměstnanců", str(len(zamestnanci)))
    souhrn.add_row("Celková doba všech směn",
                   f"{celkem_hodin:.2f} h")

    console.print(Panel(
        souhrn,
        title="[bold white]SOUHRNNÉ UKAZATELE[/bold white]",
        border_style="bright_blue"
    ))


    for z in zamestnanci:
        print(
            f"{z['zaměstnanec']:<25} "
            f"{z['číslo čipu']:<10} "
            f"{z['počet_směn']:>7} "
            f"{z['celkem_hodin']:>12.2f} "
            f"{z['průměrná_směna']:>12.2f}"
        )

    print("-" * 88)
    print(f"Počet zaměstnanců: {len(zamestnanci)}")


def vyhledej_zamestnance(zamestnanci):
    dotaz = input(
        "Zadej jméno, část jména nebo číslo čipu: "
    ).strip().casefold()

    if not dotaz:
        print("Musíš zadat hledanou hodnotu.")
        return

    nalezeni = [
        z for z in zamestnanci
        if dotaz in z["zaměstnanec"].casefold()
        or dotaz in z["číslo čipu"].casefold()
    ]

    if not nalezeni:
        print("Žádný zaměstnanec nebyl nalezen.")
        return

    for z in nalezeni:
        print(f"\n{z['zaměstnanec']} | čip {z['číslo čipu']}")
        print(f"Celkem hodin: {z['celkem_hodin']:.2f}")
        print(f"Počet směn: {z['počet_směn']}")
        print(f"Průměrná směna: {z['průměrná_směna']:.2f} h")

        print("Historie směn:")
        for smena in z["směny"]:
            print(
                f"  {smena['datum']} | "
                f"{smena['příchod']}–{smena['odchod']} | "
                f"{smena['hodiny']:.2f} h"
            )


def zobraz_denni_statistiky(statistiky):
    print("\nDENNÍ STATISTIKY")
    print("-" * 90)

    for den in statistiky:
        print(
            f"{den['datum']} | směn: {den['počet_směn']} | "
            f"první: {den['první_příchod']} "
            f"({den['čas_prvního_příchodu']}) | "
            f"poslední: {den['poslední_odchod']} "
            f"({den['čas_posledního_odchodu']}) | "
            f"průměr: {den['průměrná_délka_směny']:.2f} h"
        )


def zobraz_extremy(zaznamy):
    nejkratsi = min(zaznamy, key=lambda z: z["_hodiny"])
    nejdelsi = max(zaznamy, key=lambda z: z["_hodiny"])

    for popis, z in [
        ("Nejkratší směna", nejkratsi),
        ("Nejdelší směna", nejdelsi)
    ]:
        print(
            f"{popis}: {z['zaměstnanec']}, "
            f"{z['_prichod'].strftime(FORMAT_CASU)}, "
            f"{z['_hodiny']:.2f} h"
        )


def zobraz_zebricek(zamestnanci):
    serazeni = sorted(
        zamestnanci,
        key=lambda z: z["celkem_hodin"],
        reverse=True
    )

    print("\nŽEBŘÍČEK PODLE CELKOVÉ DOBY SMĚN")
    for poradi, z in enumerate(serazeni, start=1):
        print(
            f"{poradi:>2}. {z['zaměstnanec']:<25} "
            f"{z['celkem_hodin']:>8.2f} h"
        )


def uloz_json(zamestnanci, dny, anomalie, chyby, cesta):
    """Uloží souhrnné i odvozené údaje do JSON."""
    vystup = {
        "zdroj": str(cesta),
        "format": "Analýza docházky",
        "pocet_zamestnancu": len(zamestnanci),
        "pocet_dnu": len(dny),
        "pocet_anomalii": len(anomalie),
        "pocet_neplatnych_radku": len(chyby),
        "zamestnanci": zamestnanci,
        "denni_statistiky": dny,
        "anomalie": anomalie,
        "chyby_pri_nacitani": chyby
    }

    # Pomocné klíče začínající podtržítkem se do JSON neposílají.
    with open("vysledek.json", "w", encoding="utf-8") as soubor:
        json.dump(
            vystup,
            soubor,
            ensure_ascii=False,
            indent=4
        )

    print("Výsledky byly uloženy do souboru vysledek.json.")



def zobraz_menu():
    console.clear()

    nadpis = Text()
    nadpis.append("D O C H Á Z K A\n", style="bold bright_cyan")
    nadpis.append("WORKFORCE ANALYTICS", style="bold white")

    console.print()
    console.print(
        Panel(
            Align.center(nadpis),
            subtitle="[dim]ENTERPRISE • REPORTING SYSTEM[/dim]",
            border_style="bright_cyan",
            box=box.DOUBLE,
            padding=(1, 4)
        )
    )

    menu = Table(
        title="[bold bright_white]HLAVNÍ NABÍDKA[/bold bright_white]",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold bright_cyan",
        expand=True
    )

    menu.add_column("VOLBA", justify="center", width=8)
    menu.add_column("FUNKCE", style="white")
    menu.add_column("POPIS", style="dim")

    menu.add_row("01", "Přehled zaměstnanců",
                 "Odpracované hodiny a průměry")
    menu.add_row("02", "Vyhledávání",
                 "Jméno, čip a historie směn")
    menu.add_row("03", "Denní statistiky",
                 "První příchod a poslední odchod")
    menu.add_row("04", "Kontrola směn",
                 "Krátké a dlouhé směny")
    menu.add_row("05", "Extrémní hodnoty",
                 "Nejkratší a nejdelší směna")
    menu.add_row("06", "Výkonnostní žebříček",
                 "Pořadí podle délky směn")
    menu.add_row("07", "Export do JSON",
                 "Uložení výsledků analýzy")
    menu.add_row("08", "Informace o datech",
                 "Souhrn načtených záznamů")
    menu.add_row("00", "Ukončit aplikaci",
                 "Bezpečné ukončení")

    console.print(menu)
    console.print(
        "\n[bright_cyan]❯[/bright_cyan] "
        "[bold white]Zvol operaci [0–8]:[/bold white] ",
        end=""
    )



def main():
    if len(sys.argv) != 2:
        print("Použití: python dochazka.py dochazka.csv")
        return

    cesta = Path(sys.argv[1])

    try:
        zaznamy, chyby = nacti_data(cesta)
    except ValueError as chyba:
        print(f"CHYBA: {chyba}")
        return

    zamestnanci = vypocitej_statistiky(zaznamy)
    dny = denni_statistiky(zaznamy)
    anomalie = najdi_anomalie(zaznamy)


    console.print(Panel(
        "[bold bright_green]SYSTÉM ÚSPĚŠNĚ SPUŠTĚN[/bold bright_green]\n\n"
        f"[white]Platné záznamy:[/white] [cyan]{len(zaznamy)}[/cyan]\n"
        f"[white]Zaměstnanci:[/white] [cyan]{len(zamestnanci)}[/cyan]\n"
        f"[white]Sledované dny:[/white] [cyan]{len(dny)}[/cyan]\n"
        f"[white]Záznamy k prověření:[/white] "
        f"[yellow]{len(anomalie)}[/yellow]",
        title="[bold bright_cyan]DOCHÁZKA ANALYTICS[/bold bright_cyan]",
        subtitle="[dim]Načtení a zpracování dat dokončeno[/dim]",
        border_style="bright_green",
        box=box.DOUBLE
    ))


    if chyby:
        print(f"Upozornění: přeskočeno chybných řádků: {len(chyby)}")
        for chyba in chyby[:5]:
            print("  " + chyba)

    while True:
        zobraz_menu()
        volba = input("Vyber možnost: ").strip()

        if volba == "1":
            zobraz_prehled(zamestnanci)

        elif volba == "2":
            vyhledej_zamestnance(zamestnanci)

        elif volba == "3":
            zobraz_denni_statistiky(dny)

        
        elif volba == "4":
            console.clear()

            tabulka = Table(
                title="⚠  KONTROLA NEOBVYKLÝCH SMĚN",
                box=box.ROUNDED,
                border_style="yellow",
                header_style="bold yellow",
                show_lines=True,
                expand=True
            )

            tabulka.add_column("ZAMĚSTNANEC")
            tabulka.add_column("DATUM", justify="center")
            tabulka.add_column("PŘÍCHOD", justify="center")
            tabulka.add_column("ODCHOD", justify="center")
            tabulka.add_column("DÉLKA", justify="right")
            tabulka.add_column("UPOZORNĚNÍ")

            for a in anomalie:
                barva = (
                    "red" if a["důvod"] == "Dlouhá směna"
                    else "yellow"
                )

                tabulka.add_row(
                    a["zaměstnanec"],
                    a["datum"],
                    a["příchod"],
                    a["odchod"],
                    f"{a['hodiny']:.2f} h",
                    f"[{barva}]{a['důvod']}[/{barva}]"
                )

            if anomalie:
                console.print(tabulka)
                console.print(Panel(
                    f"Nalezeno záznamů k prověření: "
                    f"[bold yellow]{len(anomalie)}[/bold yellow]\n"
                    f"[dim]Krátká směna: méně než {KRATKA_SMENA} h. "
                    f"Dlouhá směna: více než {DLOUHA_SMENA} h.[/dim]",
                    title="[bold yellow]VÝSLEDEK KONTROLY[/bold yellow]",
                    border_style="yellow"
                ))
            else:
                console.print(Panel(
                    "[bold green]Žádné neobvyklé směny nebyly nalezeny.[/bold green]",
                    title="KONTROLA DOKONČENA",
                    border_style="green"
                ))


            if anomalie:
                for a in anomalie:
                    print(
                        f"{a['zaměstnanec']} | {a['datum']} | "
                        f"{a['hodiny']:.2f} h | {a['důvod']}"
                    )
            else:
                print("Nebyly nalezeny žádné neobvyklé směny.")

        elif volba == "5":
            zobraz_extremy(zaznamy)

        elif volba == "6":
            zobraz_zebricek(zamestnanci)

        elif volba == "7":
            try:
                uloz_json(
                    zamestnanci, dny, anomalie, chyby, cesta
                )
            except OSError as chyba:
                print(f"JSON se nepodařilo uložit: {chyba}")

        elif volba == "8":
            print(f"Vstupní soubor: {cesta}")
            print(f"Platných záznamů: {len(zaznamy)}")
            print(f"Počet zaměstnanců: {len(zamestnanci)}")
            print(f"Počet dnů: {len(dny)}")
            print(f"Počet neobvyklých směn: {len(anomalie)}")
            print(f"Počet chybných řádků: {len(chyby)}")

        elif volba == "0":
            print("Aplikace byla ukončena. Na shledanou!")
            break

        else:
            print("Neplatná volba. Zadej číslo 0 až 8.")


if __name__ == "__main__":
    main()
