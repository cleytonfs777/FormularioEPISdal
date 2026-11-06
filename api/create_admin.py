"""Cria o primeiro usuário do painel admin.

Uso (na pasta api/):
    python create_admin.py admin senha-segura
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.admin.auth import hash_senha
from app.models import SessionLocal, UsuarioAdmin, init_db, utcnow


def main() -> None:
    if len(sys.argv) < 3:
        print("Uso: python create_admin.py <username> <senha>")
        sys.exit(1)
    username, senha = sys.argv[1].strip(), sys.argv[2]
    if len(senha) < 8:
        print("A senha deve ter pelo menos 8 caracteres.")
        sys.exit(1)

    init_db()
    db = SessionLocal()
    try:
        existente = db.query(UsuarioAdmin).filter_by(username=username).first()
        if existente:
            existente.password_hash = hash_senha(senha)
            existente.ativo = True
            db.commit()
            print(f"Senha atualizada para o admin '{username}'.")
            return
        db.add(UsuarioAdmin(
            username=username,
            password_hash=hash_senha(senha),
            ativo=True,
            created_at=utcnow(),
        ))
        db.commit()
        print(f"Admin '{username}' criado. Acesse /admin/login")
    finally:
        db.close()


if __name__ == "__main__":
    main()
