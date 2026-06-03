"""Standalone Discord connectivity diagnostic.

Runs through the same steps the publisher uses (login -> fetch channel -> send)
but prints a clear, step-by-step diagnosis so connection problems are easy to
pinpoint. Reads DISCORD_TOKEN and DISCORD_CHANNEL_ID from the environment / .env.

Usage:
    # locally (with the venv active)
    python scripts/discord_diagnose.py

    # inside the running container
    docker compose exec app python scripts/discord_diagnose.py
"""

from __future__ import annotations

import asyncio
import sys

import discord

from app.core.config import get_settings


async def main() -> int:
    settings = get_settings()

    print("1) Configuración:")
    token = settings.discord_token
    channel_id = settings.discord_channel_id
    if not token:
        print("   ❌ DISCORD_TOKEN no está definido")
        return 1
    if not channel_id:
        print("   ❌ DISCORD_CHANNEL_ID no está definido")
        return 1
    print(f"   ✅ token presente (longitud={len(token)}), channel_id={channel_id}")

    intents = discord.Intents.none()
    client = discord.Client(intents=intents)
    outcome: dict[str, object] = {}

    @client.event
    async def on_ready() -> None:
        print(f"2) Login OK como: {client.user} (gateway conectado)")
        try:
            print("3) Buscando el canal...")
            channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            name = getattr(channel, "name", "?")
            print(f"   ✅ canal encontrado: #{name} ({type(channel).__name__})")
            if not isinstance(channel, discord.abc.Messageable):
                print("   ❌ el canal no admite mensajes (¿es una categoría o un canal de voz?)")
                outcome["ok"] = False
            else:
                print("4) Enviando mensaje de prueba...")
                msg = await channel.send("🔧 Diagnóstico de Anfaia Daily AI: conexión correcta.")
                print(f"   ✅ enviado, message_id={msg.id}")
                outcome["ok"] = True
        except discord.Forbidden:
            print("   ❌ 403 Forbidden: el bot no tiene permiso para ver/escribir en ese canal.")
            outcome["ok"] = False
        except discord.NotFound:
            print("   ❌ 404 Not Found: el channel_id no existe o el bot no está en ese servidor.")
            outcome["ok"] = False
        except Exception as exc:
            print(f"   ❌ error inesperado: {type(exc).__name__}: {exc}")
            outcome["ok"] = False
        finally:
            await client.close()

    try:
        async with asyncio.timeout(30):
            await client.start(token)
    except discord.LoginFailure:
        print("2) ❌ Login FALLIDO: el DISCORD_TOKEN es inválido (¿copiaste el token del Bot?).")
        return 1
    except TimeoutError:
        print("2) ❌ Timeout: no se pudo conectar al gateway (wss://gateway.discord.gg).")
        print("   Revisa la conectividad de red saliente del contenedor/máquina.")
        return 1
    except (discord.HTTPException, OSError) as exc:
        print(f"2) ❌ Error de conexión con Discord: {type(exc).__name__}: {exc}")
        return 1

    return 0 if outcome.get("ok") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
