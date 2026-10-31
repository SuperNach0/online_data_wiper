# Online Data Wiper

Application personnelle pour réduire au maximum son empreinte en ligne : data brokers, demandes RGPD, publicitaires, et suivi de tous les sites où l'on apparaît.

## Feuille de route

1. **Tableau de bord de suivi** : catalogue de data brokers et d'opt-out, statut de chaque démarche, historique, relances.
2. **Demandes RGPD** : courriers préremplis (art. 15, 17, 21), envoi par e-mail, rappel à 1 mois, modèle de plainte CNIL.
3. **Découverte** : fuites de données (Have I Been Pwned), recherche nom / pseudos, analyse d'un export de boîte mail.
4. **Multi-profils** (plus tard) : ouvrir l'outil à d'autres personnes, chacune gardant ses données.

## Lancer le tableau de bord

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

Sans configuration, le bouton « Ouvrir dans ma messagerie » prépare l'e-mail dans ton logiciel habituel. Pour envoyer directement depuis l'appli (avec une copie cachée à toi-même comme preuve), définis ces variables avant de lancer :

```bash
export WIPER_SMTP_HOST=smtp.gmail.com
export WIPER_SMTP_PORT=587
export WIPER_SMTP_USER=toi@gmail.com
export WIPER_SMTP_PASSWORD="mot de passe d'application"   # Gmail : myaccount.google.com/apppasswords
```

Chaque courrier envoyé est gardé dans l'historique de la cible.

## Découverte (étape 3)

L'onglet **Découverte** propose trois pistes :

- **Fuites de données** via Have I Been Pwned. La vérification automatique demande une clé API payante (haveibeenpwned.com/API/Key) : `export WIPER_HIBP_API_KEY=...`. Chaque fuite trouvée devient une cible dans le tableau de bord.
- **Recherche** : liens prêts vers Google, DuckDuckGo et Bing pour ton nom, tes e-mails et tes pseudos, et vers une vingtaine de réseaux pour chaque pseudo.
- **Boîte mail** : importe un export `.mbox` (Google Takeout pour Gmail). L'appli repère les expéditeurs qui ressemblent à des créations de compte (bienvenue, mot de passe, vérification…) pour retrouver les comptes oubliés. Seuls les en-têtes sont lus et le fichier est effacé après. Pour un très gros export : `.venv/bin/flask --app wiper analyser-mbox "chemin/vers/export.mbox"`

## Confidentialité

Toutes tes données (profil, statuts, notes, courriers, résultats de découverte) sont dans `instance/wiper.sqlite3`, sur ton ordinateur. Ce dossier est exclu du dépôt par `.gitignore` : rien de personnel n'est jamais poussé sur GitHub.

Le catalogue `wiper/data/cibles.json` ne contient que des informations publiques sur les organismes. Les liens d'opt-out changent souvent : si l'un d'eux est cassé, passe par la page « vie privée » du site et corrige le fichier.
