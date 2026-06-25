# OPC UA Industrial Interface

The optional OPC UA server is in:

```text
industrial/opcua_server.py
```

## Install

`asyncua` is included in the root `requirements.txt`.

## Run

Start the FastAPI backend, then:

```bash
python industrial/opcua_server.py
```

Endpoint:

```text
opc.tcp://localhost:4840/reconfactory/server/
```

## Exposed Data

- Running
- Tick
- CompletedProducts
- FaultCount
- ReroutedProducts
