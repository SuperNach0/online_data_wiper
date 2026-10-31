# Online Data Wiper

Application personnelle pour réduire au maximum son empreinte en ligne : data brokers, demandes RGPD, publicitaires, et suivi de tous les sites où l'on apparaît.

## Feuille de route

1. **Tableau de bord de suivi** : catalogue de data brokers et d'opt-out, statut de chaque démarche, historique, relances.
2. **Demandes RGPD** : courriers préremplis (art. 15, 17, 21), envoi par e-mail, rappel à 1 mois, modèle de plainte CNIL.
3. **Découverte** : fuites de données (Have I Been Pwned), recherche nom / pseudos, analyse d'un export de boîte mail.
4. **Multi-profils** : ouvrir l'outil à d'autres personnes, chacune gardant ses données.

## Lancer le tableau de bord

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m wiper
```

Puis ouvrir http://127.0.0.1:5000. L'appli n'écoute que sur ta machine.

Tests : `.venv/bin/python -m pytest`

## Confidentialité

Toutes tes données (statuts, notes, sites ajoutés) sont dans `instance/wiper.sqlite3`, sur ton ordinateur. Ce dossier est exclu du dépôt par `.gitignore` : rien de personnel n'est jamais poussé sur GitHub.

Le catalogue `wiper/data/cibles.json` ne contient que des informations publiques sur les organismes. Les liens d'opt-out changent souvent : si l'un d'eux est cassé, passe par la page « vie privée » du site et corrige le fichier.
