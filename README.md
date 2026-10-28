c_out
=====

c_out daemon

Requires Python 3.7 or newer.

Setup
-----

    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    cp config.py.example config.py   # and adjust

Run with `./runenv.sh c_outd_mqtt.py`.

systemd
-------

    sudo cp c_out.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now c_out
    journalctl -u c_out -f

The unit expects the checkout in `/home/cout/c_out` and runs as user
`cout`. Adjust `User`, `WorkingDirectory` and `ExecStart` if your setup
differs.
