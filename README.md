# CS benchmark

This has the assets for setting up the customer support/success project for benchmarking promptql


## Setup

### Pre-requisites
- Have postgres running at localhost:5432 with postgres:postgres as credentials. Ensure `psql` and `createdb` commands are available.
- Install poetry
```bash
curl -sSL https://install.python-poetry.org | python3 -
```
- Set your Anthropic key in the ANTHROPIC_API_KEY env var
- Set your OpenAI key in the OPENAI_API_KEY env var
- Set your PromptQL key in the PROMPTQL_SECRET_KEY env var

### Database setup

Control Plane data:
- DB name: "control_plane_new"
- Dump file: control_plane_dump.sql

```bash
createdb -h localhost -U postgres control_plane_new
psql -h localhost -U postgres -d control_plane_new -f control_plane_dump.sql
```

- Support tickets data:
- DB name: "support_tickets_new"
- Dump file: support_tickets_dump_feb3.sql

```bash
createdb -h localhost -U postgres support_tickets_new
psql -h localhost -U postgres -d support_tickets_new -f support_tickets_dump_feb3.sql
```

### Running PromptQL

```bash
cd my-assistant
docker compose up -d
ddn console --local
```

### Running o1 and o3-mini

- Ensure python dependencies are installed
```bash
poetry install
```

- Run the model
```bash
poetry run python o1_eval.py --model <o1|o3-mini>
```