import os
import asyncio
import pandas as pd
from telethon import TelegramClient
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from datetime import datetime
import uuid
import socks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_ID = 38740867
API_HASH = "41c4a919ccabb01165c49a310f8709c2"
SESSION_NAME = "my_account"

class Parser:
    def __init__(self):
        self.tasks = {}
        self.log_queues = {}
        self.cancel_flags = {}

    async def _get_client(self, proxy_str=None):
        client_args = {
            "session": os.path.join(BASE_DIR, "backend", "sessions", SESSION_NAME),
            "api_id": API_ID,
            "api_hash": API_HASH,
            "connection_retries": None,
        }

        if proxy_str:
            proxy_str = proxy_str.replace("socks5://", "").strip()
            parts = proxy_str.split(":")
            proxy_dict = {
                "proxy_type": socks.SOCKS5,
                "addr": parts[0],
                "port": int(parts[1])
            }
            if len(parts) == 4:
                proxy_dict["username"] = parts[2]
                proxy_dict["password"] = parts[3]
            client_args["proxy"] = (
                proxy_dict["proxy_type"],
                proxy_dict["addr"],
                proxy_dict["port"],
                True,
                proxy_dict.get("username"),
                proxy_dict.get("password")
            )

        client = TelegramClient(**client_args)
        await client.connect()
        if not await client.is_user_authorized():
            print("Сессия не авторизована!")
            exit(1)
        return client

    async def start_parsing(self, session_name, target, limit, online_only, recent_days, letter, use_proxy=False, proxy=None):
        task_id = str(uuid.uuid4())
        queue = asyncio.Queue()
        self.log_queues[task_id] = queue
        self.tasks[task_id] = {"users": set()}
        self.cancel_flags[task_id] = False

        asyncio.create_task(self._worker(task_id, target, limit, online_only, recent_days, letter, queue, use_proxy, proxy))
        return task_id

    def stop_task(self, task_id):
        self.cancel_flags[task_id] = True

    async def _auto_join(self, client, target, queue):
        try:
            if target.startswith("https://t.me/+"):
                hash_invite = target.split("/")[-1]
                await queue.put({"type": "log", "message": "Приватная ссылка — вступаем..."})
                await client(ImportChatInviteRequest(hash_invite))
                await queue.put({"type": "log", "message": "Успешно вступили"})
                return True

            username = target.replace("https://t.me/", "").replace("@", "").split("?")[0].split("/")[0]
            entity = await client.get_entity(username)
            if getattr(entity, "left", False):
                await queue.put({"type": "log", "message": "Вступаем..."})
                await client(JoinChannelRequest(entity))
                await asyncio.sleep(3)
            return True
        except Exception as e:
            await queue.put({"type": "log", "message": f"Вступление: {str(e)}"})
            return "USER_ALREADY_PARTICIPANT" not in str(e)

    async def _worker(self, task_id, target, limit, online_only, recent_days, letter, queue, use_proxy, proxy):
        client = await self._get_client(proxy if use_proxy else None)
        total = 0
        seen = set()

        try:
            await self._auto_join(client, target, queue)
            entity = await client.get_entity(target)
            title = getattr(entity, "title", target)
            await queue.put({"type": "log", "message": f"В чате: {title} — скроллим историю"})

            async for message in client.iter_messages(entity, limit=None):
                if self.cancel_flags.get(task_id, False):
                    await queue.put({"type": "log", "message": "Остановлено пользователем"})
                    break
                if limit and total >= limit:
                    break
                if total % 100 == 0 and total > 0:
                    await queue.put({"type": "progress", "parsed": total})

                if not message.sender_id:
                    continue

                try:
                    sender = await message.get_sender()
                except:
                    continue

                if not sender or sender.bot or sender.deleted or sender.is_self:
                    continue

                uid = sender.id
                if uid in seen:
                    continue
                seen.add(uid)

                name_ok = True
                if letter:
                    name = f"{sender.first_name or ''}{sender.last_name or ''}{sender.username or ''}".lower()
                    name_ok = name.startswith(letter)

                online_ok = True
                if online_only or recent_days > 0:
                    if hasattr(sender.status, "was_online"):
                        days = (datetime.now() - sender.status.was_online.replace(tzinfo=None)).days
                        if online_only and days > 0: online_ok = False
                        if recent_days > 0 and days > recent_days: online_ok = False
                    else:
                        online_ok = False

                if name_ok and online_ok:
                    self.tasks[task_id]["users"].add((
                        uid,
                        sender.username or "",
                        sender.first_name or "",
                        sender.last_name or "",
                        sender.phone or ""
                    ))
                    total += 1

            status = "stopped" if self.cancel_flags.get(task_id, False) else "finished"
            msg = f"Остановлено. Найдено {total}" if status == "stopped" else f"ГОТОВО! Найдено {total} человек"
            await queue.put({"type": status, "message": msg, "count": total})

            df = pd.DataFrame([{
                "id": uid,
                "username": u,
                "first_name": f,
                "last_name": l,
                "phone": p
            } for uid, u, f, l, p in self.tasks[task_id]["users"]])

            res_dir = os.path.join(BASE_DIR, "backend", "results")
            os.makedirs(res_dir, exist_ok=True)
            for ext in ["csv", "xlsx"]:
                path = os.path.join(res_dir, f"{task_id}.{ext}")
                getattr(df, f"to_{'excel' if ext == 'xlsx' else 'csv'}")(path, index=False)

        except Exception as e:
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await client.disconnect()

    def get_result_file(self, task_id, format):
        path = os.path.join(BASE_DIR, "backend", "results", f"{task_id}.{format}")
        return path if os.path.exists(path) else None

    def get_log_queue(self, task_id):
        return self.log_queues.get(task_id)

parser = Parser()