# Online Data Wiper

Application personnelle pour réduire au maximum son empreinte en ligne : data brokers, demandes RGPD, publicitaires, et suivi de tous les sites où l'on apparaît.

## Feuille de route

1. **Tableau de bord de suivi** : catalogue de data brokers et d'opt-out, statut de chaque démarche, historique, relances.
2. **Demandes RGPD** : courriers préremplis (art. 15, 17, 21), envoi par e-mail, rappel à 1 mois, modèle de plainte CNIL.
3. **Découverte** : fuites de données (Have I Been Pwned), recherche nom / pseudos, analyse d'un export de boîte mail.
4. **Multi-profils** (plus tard) : ouvrir l'outil à d'autres personnes, chacune gardant ses données.

## Installation sous Windows (le plus simple)

1. Va dans [Releases](https://github.com/SuperNach0/online_data_wiper/releases/latest) et télécharge **OnlineDataWiper.exe**.
2. Double-clique dessus. Si Windows affiche « Windows a protégé votre ordinateur », clique sur « Informations complémentaires » puis « Exécuter quand même » (l'exe n'est pas signé, c'est normal pour un outil perso).
3. L'appli s'installe toute seule dans `%LOCALAPPDATA%\Programs\OnlineDataWiper`, crée un raccourci dans le menu Démarrer et sur le bureau, puis s'ouvre dans sa propre fenêtre (plus de navigateur ni de fenêtre noire). Tu peux supprimer l'exe téléchargé.
4. Au premier lancement, un **assistant en 3 écrans** te demande ton nom, ton e-mail et un mot de passe d'application (liens directs pour Gmail, Outlook, Yahoo, iCloud). Il teste la connexion, puis tout démarre tout seul.

Fermer la fenêtre ne coupe pas l'appli : elle reste près de l'horloge (icône bouclier) et continue son travail. Clic droit sur l'icône > **Quitter** pour l'arrêter vraiment. Elle se relance au démarrage de Windows, en arrière-plan (désactivable dans Pilote automatique).

Tes données sont dans `%APPDATA%\OnlineDataWiper` (copie ce dossier pour faire une sauvegarde). Pour une nouvelle version, télécharge le nouvel exe et double-clique : il remplace l'ancien et garde tes données.

## Pilote automatique

Une fois l'assistant terminé, l'appli fait tout ce qu'elle peut sans toi, **toutes les 4 heures** :

1. Analyse ta boîte mail (en-têtes seulement, lecture seule, une fois par semaine) pour trouver les comptes que tu as créés au fil des années.
2. Envoie les demandes RGPD depuis ton adresse aux data brokers et aux comptes inactifs depuis plus d'un an (40 envois maximum par passage). Les adresses de contact viennent d'un annuaire de ~2 500 organismes (base libre [datarequests.org](https://www.datarequests.org), licence CC0, régénérée par `outils/construire_annuaire.py`).
3. Lit les réponses (statut « Réponse reçue »), repère les adresses qui rebondissent, relance à 30 jours et vérifie les fuites chaque semaine.
4. Te prévient par une notification Windows quand il se passe quelque chose d'important.

Chaque étape se coupe dans **Pilote automatique > Automatisation**. Ce qui reste manuel est regroupé dans **À faire par toi** : formulaires web avec captcha, réglages dans tes comptes Google/Meta/Amazon, réponses qui demandent une pièce d'identité, et dépôt des plaintes CNIL (texte prêt). L'onglet **Bilan** résume tout ce qui a été fait.

## Lancer depuis le code (développement)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m wiper
```

Puis ouvrir http://127.0.0.1:5000. L'appli n'écoute que sur ta machine.

Tests : `.venv/bin/python -m pytest`

Commence par remplir **Mon profil** (nom, e-mails, pseudos) : il sert aux courriers et à la découverte.

## Courriers RGPD (étape 2)

Chaque cible a un bouton « Courrier » : accès + effacement + opposition (le plus complet), accès seul, opposition seule, relance, et texte de plainte CNIL. Le courrier proposé change selon l'avancement : relance après 30 jours sans réponse, plainte CNIL 15 jours après la relance.

Sans configuration, le bouton « Ouvrir dans ma messagerie » prépare l'e-mail dans ton logiciel habituel. Pour envoyer directement depuis l'appli (avec une copie cachée à toi-même comme preuve), renseigne ton e-mail et un mot de passe d'application dans l'onglet **Réglages**. Le serveur des messageries courantes (Gmail, Outlook, Orange, Free, SFR, La Poste…) est détecté automatiquement. Les variables d'environnement restent possibles et passent en priorité :

```bash
export WIPER_SMTP_HOST=smtp.gmail.com
export WIPER_SMTP_PORT=587
export WIPER_SMTP_USER=toi@gmail.com
export WIPER_SMTP_PASSWORD="mot de passe d'application"   # Gmail : myaccount.google.com/apppasswords
```

Chaque courrier envoyé est gardé dans l'historique de la cible.

## Découverte (étape 3)

L'onglet **Découverte** propose trois pistes :

- **Fuites de données** via Have I Been Pwned. La vérification automatique demande une clé API payante (haveibeenpwned.com/API/Key), à saisir dans **Réglages** (ou `WIPER_HIBP_API_KEY`). Chaque fuite trouvée devient une cible dans le tableau de bord.
- **Recherche** : liens prêts vers Google, DuckDuckGo et Bing pour ton nom, tes e-mails et tes pseudos, et vers une vingtaine de réseaux pour chaque pseudo.
- **Boîte mail** : importe un export `.mbox` (Google Takeout pour Gmail). L'appli repère les expéditeurs qui ressemblent à des créations de compte (bienvenue, mot de passe, vérification…) pour retrouver les comptes oubliés. Seuls les en-têtes sont lus et le fichier est effacé après. Pour un très gros export : `.venv/bin/flask --app wiper analyser-mbox "chemin/vers/export.mbox"`

## Confidentialité

Toutes tes données (profil, statuts, notes, courriers, réglages, résultats de découverte) sont dans un fichier `wiper.sqlite3` sur ton ordinateur : `%APPDATA%\OnlineDataWiper` avec l'exe, `instance/` depuis le code. L'appli n'écoute que sur 127.0.0.1 et refuse les formulaires venant d'un autre site. Ce dossier est exclu du dépôt par `.gitignore` : rien de personnel n'est jamais poussé sur GitHub.

Le catalogue `wiper/data/cibles.json` ne contient que des informations publiques sur les organismes. Les liens d'opt-out changent souvent : si l'un d'eux est cassé, passe par la page « vie privée » du site et corrige le fichier.
