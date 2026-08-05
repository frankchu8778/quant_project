# 使用Python 3.12作为基础镜像
FROM python:3.12-slim
# 设置时区
ENV TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY panda_common/ /app/panda_common/
COPY panda_data/ /app/panda_data/
COPY panda_data_hub/ /app/panda_data_hub/
COPY panda_factor/ /app/panda_factor/
COPY panda_factor_server/ /app/panda_factor_server/
COPY requirements.txt /app/

# 清理构建文件
RUN for dir in panda_common panda_data panda_factor panda_factor_server panda_mq; do \
    rm -rf $dir/dist/* $dir/build/* $dir/*.egg-info; \
    done

# 安装项目依赖
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 安装项目包
WORKDIR /app/panda_common
RUN pip install  .

WORKDIR /app/panda_data
RUN pip install  .

WORKDIR /app/panda_data_hub
RUN pip install  .

WORKDIR /app/panda_factor
RUN pip install  .

WORKDIR /app/panda_factor_server
RUN pip install  .
