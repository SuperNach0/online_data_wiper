from . import create_app

if __name__ == "__main__":
    # 127.0.0.1 uniquement : le tableau de bord n'est jamais exposé sur le réseau.
    create_app().run(host="127.0.0.1", port=5000, debug=False)
