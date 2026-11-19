"""MQTT subscriber. One process, one SQLite file, no outbound payment call."""

import logging

from meowmap_backend.config import Config
from meowmap_backend.db import connect
from meowmap_backend.ingest import ingest
from meowmap_backend.ordering import create_approval_requests

log = logging.getLogger(__name__)


def serve(cfg: Config) -> None:
    import paho.mqtt.client as mqtt

    conn = connect(cfg.sqlite_path)

    def on_connect(client, userdata, flags, reason_code, properties):
        del userdata, flags, properties
        if reason_code != 0:
            log.error("mqtt connect failed: %s", reason_code)
            return
        client.subscribe(cfg.topic_meow)
        client.subscribe(cfg.topic_vote)
        log.info("subscribed to %s and %s", cfg.topic_meow, cfg.topic_vote)

    def on_message(client, userdata, msg):
        del client, userdata
        status = ingest(conn, msg.topic, msg.payload, cfg)
        log.info("ingest %s (%s bytes) -> %s", msg.topic, len(msg.payload), status)
        if status != "stored":
            return
        for row in create_approval_requests(conn):
            log.info(
                "approval request %s stored; delivery not sent; payment_status=%s",
                row["id"],
                row["payment_status"],
            )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt_user:
        client.username_pw_set(cfg.mqtt_user, cfg.mqtt_password)
    client.on_connect = on_connect
    client.on_message = on_message
    log.info("connecting to mqtt %s:%s", cfg.mqtt_host, cfg.mqtt_port)
    client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
    client.loop_forever()
