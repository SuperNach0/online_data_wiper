"""Modèles de courriers RGPD, remplis avec le profil et la cible."""
from datetime import date

from jinja2 import Environment, StrictUndefined

_env = Environment(autoescape=False, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)

_IDENTITE = """{{ p.prenom or '' }} {{ p.nom or '' }}
{% if p.adresse %}{{ p.adresse }}
{% endif %}
{% for e in emails %}{{ e }}
{% endfor %}"""

_DONNEES = """Pour vous permettre de me retrouver dans vos fichiers, voici les informations me concernant que vous êtes susceptibles de détenir :
- Nom : {{ p.prenom or '' }} {{ p.nom or '' }}
{% for e in emails %}- Adresse e-mail : {{ e }}
{% endfor %}
{% if p.adresse %}- Adresse postale : {{ p.adresse }}
{% endif %}
{% if p.telephone %}- Téléphone : {{ p.telephone }}
{% endif %}
{% if p.date_naissance %}- Date de naissance : {{ p.date_naissance }}
{% endif %}

Ces informations ne doivent être utilisées que pour traiter la présente demande."""

MODELES = {
    "effacement": {
        "label": "Accès + effacement + opposition (recommandé)",
        "objet": "Demande d'accès, d'effacement et d'opposition (RGPD art. 15, 17 et 21)",
        "corps": """Madame, Monsieur,

En application du Règlement général sur la protection des données (RGPD), je vous adresse les demandes suivantes concernant {{ c.nom }} :

1. Droit d'accès (article 15) : me communiquer l'ensemble des données personnelles me concernant que vous détenez, leur source, les finalités du traitement, la durée de conservation et la liste des destinataires à qui elles ont été transmises ou vendues.

2. Droit d'opposition (article 21) : je m'oppose à tout traitement de mes données à des fins de prospection, de profilage et de publicité ciblée.

3. Droit à l'effacement (article 17) : supprimer l'ensemble de ces données, y compris dans les fichiers transmis à vos partenaires, que vous devrez informer de ma demande conformément à l'article 19.

""" + _DONNEES + """

Conformément à l'article 12, vous disposez d'un délai d'un mois à compter de la réception de ce courrier pour y répondre. À défaut, je me réserve le droit de saisir la CNIL.

Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.

""" + _IDENTITE,
    },
    "acces": {
        "label": "Droit d'accès seul (art. 15)",
        "objet": "Demande d'accès à mes données personnelles (RGPD art. 15)",
        "corps": """Madame, Monsieur,

En application de l'article 15 du RGPD, je vous demande de me communiquer l'ensemble des données personnelles me concernant que vous détenez, ainsi que :
- les finalités du traitement ;
- la source de ces données lorsqu'elles n'ont pas été collectées auprès de moi ;
- les destinataires à qui elles ont été communiquées ;
- leur durée de conservation.

""" + _DONNEES + """

Vous disposez d'un délai d'un mois pour répondre (article 12).

Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.

""" + _IDENTITE,
    },
    "opposition": {
        "label": "Opposition à la prospection seule (art. 21)",
        "objet": "Opposition au traitement de mes données à des fins de prospection (RGPD art. 21)",
        "corps": """Madame, Monsieur,

En application de l'article 21 du RGPD, je m'oppose à tout traitement de mes données personnelles à des fins de prospection commerciale, de profilage et de publicité ciblée, par vous-même comme par vos partenaires.

Je vous demande de m'inscrire sur votre liste d'opposition et de me confirmer la prise en compte de cette demande.

""" + _DONNEES + """

Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.

""" + _IDENTITE,
    },
    "relance": {
        "label": "Relance après un mois sans réponse",
        "objet": "Relance : demande RGPD restée sans réponse",
        "corps": """Madame, Monsieur,

Le {{ date_envoi }}, je vous ai adressé une demande d'accès, d'effacement et d'opposition concernant mes données personnelles, sur le fondement des articles 15, 17 et 21 du RGPD.

Le délai d'un mois prévu par l'article 12 est dépassé et je n'ai reçu aucune réponse satisfaisante.

Je vous demande de traiter cette demande sans délai. Sans réponse de votre part sous quinze jours, je saisirai la Commission nationale de l'informatique et des libertés (CNIL).

""" + _DONNEES + """

Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.

""" + _IDENTITE,
    },
    "plainte_cnil": {
        "label": "Texte de plainte CNIL",
        "objet": "Plainte : absence de réponse à une demande RGPD ({{ c.nom }})",
        "corps": """À déposer sur https://www.cnil.fr/fr/plaintes (joindre une copie de la demande initiale, de la relance et des éventuelles réponses).

Organisme mis en cause : {{ c.nom }}{{ ' (' ~ c.site ~ ')' if c.site else '' }}


Le {{ date_envoi }}, j'ai adressé à cet organisme une demande d'accès, d'effacement et d'opposition (articles 15, 17 et 21 du RGPD){{ " à l'adresse " ~ c.contact_rgpd if c.contact_rgpd else '' }}.{{ " Je l'ai relancé le " ~ date_relance ~ "." if date_relance else '' }}

À ce jour, le délai d'un mois prévu par l'article 12 du RGPD est dépassé et ma demande n'a pas été traitée. Je demande à la CNIL d'intervenir pour que cet organisme me communique les données qu'il détient sur moi, cesse de les utiliser à des fins de prospection et les efface.

""" + _IDENTITE,
    },
}


def _fr(iso):
    if not iso:
        return "[date]"
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def rediger(type_courrier, profil, cible):
    m = MODELES[type_courrier]
    emails = [e.strip() for e in (profil["emails"] or "").splitlines() if e.strip()]
    ctx = {
        "p": profil, "c": cible, "emails": emails,
        "date_envoi": _fr(cible["date_envoi"]),
        "date_relance": _fr(cible["date_relance"]) if cible["date_relance"] else None,
    }
    return {
        "objet": _env.from_string(m["objet"]).render(ctx).strip(),
        "corps": _env.from_string(m["corps"]).render(ctx).strip() + "\n",
    }


def profil_incomplet(profil):
    return not (profil["nom"] and (profil["emails"] or "").strip())
