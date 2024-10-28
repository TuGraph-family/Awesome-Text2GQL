# TuGraph-DB ChatBot

TuGraph-DB ChatBot is a demo which can intercract with the TuGraph-DB.You can input what you want to operate the db,such as querying or creating data. And The ChatBot will also help you to excute the cypher too. Let's trying it now!

[!demo](../images/demo.gif)
## Requirements

GPU V100 16G

## Quick Start

### Preparation

#### TuGraph-DB
[TuGraph-DB](https://github.com/TuGraph-family/tugraph-db)

##### pull docker image
```
docker pull tugraph/tugraph-compile-ubuntu18.04
```

```
export VERSION=latest
export REPOSITORY=docker.io/tugraph/tugraph-compile-ubuntu18.84 # path to your docker image
```
Start Docker
```
docker run -dt --gpus -p 7070:7070  -p 7687:7687 -p 9090:9090 -v /root/tugraph/data:/var/lib/lgraph/data  -v /root/tugraph/log:/var/log/lgraph_log \
 --name demo ${REPOSITORY}:${VERSION} /bin/bash

docker exec -it demo bash
 ```

##### change the defalut python3.6 into python3.10
```
apt update
```

```
apt install software-properties-common
add-apt-repository ppa:deadsnakes/ppa
apt update
apt install python3.10
```
set python3.10 as the default python.
```
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.6 1
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2
update-alternatives --config python3
```
verify
```
python3 --version
```
##### Create WorkRepo
```
mkdir work_repo
cd work_repo
```

##### Build TuGraph-DB From Source
```
git clone --recursive https://github.com/TuGraph-family/tugraph-db.git
cd tugraph-db
deps/build_deps.sh
mkdir build && cd buildimages/demo.mp4
cmake .. -DOURSYSTEM=ubuntu
make
make package
```

#### DB-GPT-GQL
[DB-GPT-GQL](https://github.com/eosphoros-ai/DB-GPT-Hub/blob/main/src/dbgpt-hub-gql/)
Attention:
Before you excute training、inference or evaluation, makedir for outputs:
```
cd output
mkdir logs
mkdir adapter
mkdir pred
```

#### Generate Dataset
After install the environment of DB-GPT_GQL,
Following to build your first dataset.
```
tugraph-db/
|-train.json
|-dev.json
|-gold_dev.txt
```

### Fine-tuning
```
cd DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt-hub-gql
cp path/to/tugraph-db/ ./data  # path to your tugraph-db dataset you built above.
```

### Run Demo
start TuGraph-DB

```
cd DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt-hub-gql
mkdir demo
cp path/to/demo/ ./demo
cp tugraph-db  ./demo
```