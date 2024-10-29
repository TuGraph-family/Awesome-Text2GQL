# TuGraph-DB ChatBot

TuGraph-DB ChatBot is a demo which can intercract with the TuGraph-DB.You can input what you want to operate the db,such as querying or creating data. And The ChatBot will also help you to excute the cypher too. Let's trying it now!

![demo](https://github.com/Panghy1106/Awesome-Text2GQL/blob/dev_demo/images/demo.gif)

## Requirements

GPU V100 16G

系统盘100G(recommended) 
minimum requirements: 系统盘30G，数据盘60G。

## Quick Start

### Preparation

#### Install Nvidia Docker
Nvidia Docker allows you to use NVIDIA GPU in docker.
Here is the installation method to install Nvidia Docker in CentOS7.You can install Nvidia Docker in ubuntu system as well,you need to find the installation method by yourself.Make sure you have installed Nvidia Docker before you start the container of tugraph-db-runtime image in the following step.
```
distribution=$(. /etc/os-release;echo$ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.repo | sudo tee /etc/yum.repos.d/nvidia-docker.repo

sudo yum install -y nvidia-docker2
sudo pkill -SIGHUP dockerd
```
restart docker
```
sudo systemctl restart docker
```

#### TuGraph-DB
[TuGraph-DB](https://github.com/TuGraph-family/tugraph-db)

##### pull docker image
```
docker pull tugraph/tugraph-runtime-ubuntu18.04
```
set environment variables
```
export VERSION=latest
export REPOSITORY=docker.io/tugraph/tugraph-runtime-ubuntu18.84 # path to your docker image
```
Start Docker
```
docker run -dt --gpus -p 7070:7070  -p 7687:7687 -p 9090:9090 -v /root/tugraph/data:/var/lib/lgraph/data  -v /root/tugraph/log:/var/log/lgraph_log \
 --name demo ${REPOSITORY}:${VERSION} /bin/bash

docker exec -it demo bash

#--gpus means enabling gpus in the docker container
```
verify you can use gpu in the docker container
you will see the information of gpu after you input the instruction bellow. If you can't see the gpu information, back to the the steps before to make sure you have installed Nvidia-Docker successfully and started docker with `--gpus`.
```
nvidia-smi
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
In the last step, you will see a list,choose python3.10 as the default python version.

verify python version
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

##### 安装gpu的相关支持 in the container

```
nvidia-smi
```

#### DB-GPT-GQL
[DB-GPT-GQL](https://github.com/eosphoros-ai/DB-GPT-Hub/blob/main/src/dbgpt-hub-gql/)
Attention:
Before you excute training、inference or evaluation, mkdir for outputs:
```
cd ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql
mkdir ./output/logs
mkdir ./output/adapter
mkdir ./output/pred
```

#### Generate Dataset
After installing the environment of DB-GPT_GQL,
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
cp dynamic link library of python client compiled in ./tugraph-db before into the demo directory in  
```
cd path/to/work_repo/
cp ./Awesome-Text2GQL/demo ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/
cp ./tugraph-db/output/liblgraph_client_cpp_rpc.so  ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/
cp ./tugraph-db/output/liblgraph_client_python.so  ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/
```
start tugraph-db
```
lgraph_server -c /usr/local/etc/lgraph.json -d start
```
import data
```
heihei
```

### Q&A
#### 1. 30G系统盘和60G数据盘 solution
#### 2. 版本匹配 tugraph-db-example
transformers 4.44.2, 版本不能太高。
transformers 4.44.2,