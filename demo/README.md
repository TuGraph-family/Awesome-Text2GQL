# TuGraph-DB ChatBot

TuGraph-DB ChatBot is a demo which can intercract with the TuGraph-DB.You can input how you want to operate the db in Chinese, such as querying or creating data. And The ChatBot will also help you to excute the cypher too. Let's try it now!

![demo](../images/demo.gif)

## Requirements

The README.md has been tested in: 

- **GPU**:  V100 16G-RAM

- **OS**: CentOS7

- **Disk**:  System Disk 100G (minimum requirements: System Disk 30G，Data Disk 60G. )

- **Awesome-Text2GQL**: helps to generate dataset for fine-tuning LLMs.

- **TuGraph-DB**: [TuGraph-DB](https://github.com/TuGraph-family/tugraph-db)

- **DB-GPT-GQL**: [DB-GPT-GQL](https://github.com/eosphoros-ai/DB-GPT-Hub/blob/main/src/dbgpt-hub-gql/README.zh.md) 

## Quick Start

### Preparation

#### 1. Install Nvidia Docker

`Nvidia Docker` allows you to use NVIDIA GPU in docker.
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

#### 2. compile-docker

[TuGraph-DB](https://github.com/TuGraph-family/tugraph-db)



##### pull docker image

```
docker pull tugraph/tugraph-compile-centos7
```

set environment variables

```
export VERSION=latest
export REPOSITORY=docker.io/tugraph/tugraph-compile-centos7 # path to your docker image
```

Start runtime Docker

```
docker run -dt --gpus all -p 7070:7070  -p 7687:7687 -p 9090:9090 -v /root/tugraph/data:/var/lib/lgraph/data  -v /root/tugraph/log:/var/log/lgraph_log \
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

python3.10 is required for

```
# install dependency package
yum groupinstall "Development Tools"
yum install openssl-devel bzip2-devel libffi-devel
# bulid Python3.10 from source
wget https://www.python.org/ftp/python/3.10.15/Python-3.10.15.tgz

tar xzf Python-3.10.15.tgz

cd Python-3.10.15
./configure --enable-optimizations
make altinstall
# verify
python3.10 --version
```

set python3.10 as the default python.

```
update-alternatives --install /usr/local/bin/python3 python3 /usr/local/bin/python3.6 1
update-alternatives --install /usr/local/bin/python3 python3 /usr/local/bin/python3.10 2
update-alternatives --config python3
```

In the last step, you will see a list,choose python3.10 as the default python version.

verify python version

```
python3 --version
```

install cython

```
wget https://github.com/cython/cython/archive/refs/tags/3.0.11.tar.gz
tar xzf 3.0.11.tar.gz
cd cython-3.0.11
python3 setup.py install
```

##### Build TuGraph-DB From Source

```
mkdir work_repo && cd work_repo
git clone --recursive https://github.com/TuGraph-family/tugraph-db.git
cd tugraph-db
deps/build_deps.sh
mkdir build && cd build
cmake .. -DOURSYSTEM=centos7
make
make package
```

#### 3. Generate Dataset

##### Install MiniConda

```
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

bash Miniconda3-latest-Linux-x86_64.sh
# verify
conda --version

conda create -n demo python=3.10 
```

restart your shell or terminal to make your settings take effect.

```
conda activate demo
```

##### Awesome-Text2GQL to generate dataset

Following to build your first dataset.

```
cd /path/to/work_repo/Awesome-Text2GQL
mkdir tugraph-db
```

```
tugraph-db/
|-train.json
|-dev.json
|-gold_dev.txt
```

#### 4. DB-GPT-GQL

[DB-GPT-GQL](https://github.com/eosphoros-ai/DB-GPT-Hub/blob/main/src/dbgpt-hub-gql/)
Attention:
Before you excute training、inference or evaluation, mkdir for outputs:

```
cd ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql
mkdir -p ./output/logs ./output/adapter ./output/pred
```

### Fine-tuning

```
cd DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt-hub-gql
cp path/to/tugraph-db/ ./data  # path to your tugraph-db dataset you built above.
```

### Run Demo

cp dynamic link library of python client compiled in ./tugraph-db before into the demo directory in  

```
cd path/to/work_repo/
mkdir -p ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/

cd ./Awesome-Text2GQL/demo
cp * path/to/work_repo/DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/

cd path/to/work_repo/
cp ./tugraph-db/build/output/liblgraph_client_cpp_rpc.so  ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/
cp ./tugraph-db/build/output/liblgraph_client_python.so  ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/
cp ./tugraph-db/build/output/lgraph_import  ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/
cp -r ./tugraph-db/demo/movie ./DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo/

cd DB-GPT-Hub/src/dbgpt-hub-gql/dbgpt_hub_gql/demo
```

import data

```
mkdir -p /var/lib/lgraph/
./lgraph_import --dir /var/lib/lgraph/movie_db --verbose 2 -c ./movie/import.json --continue_on_error 1 --overwrite 1 --online false
rm -rf import_tmp
```

start tugraph-db

```
path/to/work_repo/tugraph-db/build/output/lgraph_server -c ./lgraph.json -d start
```

run demo

```
cd ..
cd ..
sh ./dbgpt_hub_gql/demo/demo.sh
```

stop server

```
path/to/work_repo/tugraph-db/build/output/lgraph_server -c ./lgraph.json -d stop
```

## Q&A

### 1. 30G系统盘和60G数据盘 solution

### 2. 版本匹配 tugraph-db-example

transformers 4.44.2, 版本不能太高。
transformers 4.44.2,

3. If you can't build TuGraph-DB from Source, please refer to the [Dockerfile](https://github.com/TuGraph-family/tugraph-db/blob/master/ci/images/tugraph-compile-ubuntu18.04-Dockerfile) of tugraph-complie-ubuntu18.04 image.