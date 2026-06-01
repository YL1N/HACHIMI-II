# EEDI 远程 Embedding 服务部署说明
目标：把 `Qwen/Qwen3-Embedding-8B` 部署在 Linux 服务器上，对外提供 OpenAI-compatible 的 `/v1/embeddings` 接口，让本地 EEDI 官方评测里的 `sim-text` 走远程 embedding，不再在办公本本地加载 8B 模型。

如果你已经有现成在线 embedding 服务，也可以不自己部署服务器。只要它提供 OpenAI-compatible 的 `/v1/embeddings` 接口，就可以直接接到当前代码里。

## 1. 服务器环境
建议：
- Linux
- NVIDIA GPU
- 已安装 CUDA
- Python 3.10+

## 2. 服务器安装
建议单独开一个环境：

```bash
python -m venv ~/venvs/qwen3_embed
source ~/venvs/qwen3_embed/bin/activate
pip install -U pip
pip install vllm
```

如果你服务器已有现成 Python 环境，也可以直接在已有环境里装。

## 3. 启动 embedding 服务
最小命令：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-Embedding-8B \
  --task embed \
  --served-model-name Qwen/Qwen3-Embedding-8B \
  --host 0.0.0.0 \
  --port 8000
```

如果你想后台跑：

```bash
nohup python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-Embedding-8B \
  --task embed \
  --served-model-name Qwen/Qwen3-Embedding-8B \
  --host 0.0.0.0 \
  --port 8000 \
  > qwen3_embedding_server.log 2>&1 &
```

说明：
- `--task embed` 很关键，它告诉 `vLLM` 这是 embedding 服务，不是聊天服务。
- `--served-model-name` 建议和本地配置里写的一致，省得混淆。

参考：
- Qwen 官方模型卡：https://huggingface.co/Qwen/Qwen3-Embedding-8B
- vLLM OpenAI-compatible server 文档：https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

## 4. 在服务器上先自测
服务起来后，在服务器本机执行：

```bash
curl http://127.0.0.1:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "model": "Qwen/Qwen3-Embedding-8B",
    "input": ["hello world", "math tutoring dialogue"]
  }'
```

如果正常，会返回一个 JSON，其中 `data` 里有两条 embedding 向量。

## 5. 本地端口转发
如果服务器不能直接暴露公网端口，建议本地做 SSH 转发：

```bash
ssh -N -L 8000:127.0.0.1:8000 your_user@your_server_host
```

这样你本地就能通过：

```text
http://127.0.0.1:8000/v1
```

访问服务器上的 embedding 服务。

## 6. 本地配置怎么填
改 [run_local.json](D:/Study/sii/MathStudent/eedi/configs/run_local.json)：

```json
{
  "embedding_api_base_url": "http://127.0.0.1:8000/v1",
  "embedding_model": "Qwen/Qwen3-Embedding-8B",
  "embedding_api_key": "EMPTY",
  "embedding_batch_size": 16
}
```

如果你用的是现成在线服务，比如：

```json
{
  "embedding_api_base_url": "https://ai.gitee.com/v1",
  "embedding_model": "Qwen3-Embedding-8B",
  "embedding_api_key": "YOUR_ACCESS_TOKEN",
  "embedding_batch_size": 16
}
```

说明：
- 如果你用 SSH 转发到本地，就是 `http://127.0.0.1:8000/v1`
- 如果你直接开放服务器端口，就换成服务器地址，比如 `http://your_server_ip:8000/v1`
- `embedding_api_key` 如果服务没鉴权，也建议填个 `EMPTY`，和测试命令保持一致

## 7. 本地先做评测 preflight
先不要直接跑全量评测，先测参数链：

```bash
python eedi/run_official_eval_with_qwen.py \
  --preflight_only \
  --evaluations sim-text,sim-corr-errs \
  --embedding_api_base_url http://127.0.0.1:8000/v1 \
  --embedding_model Qwen/Qwen3-Embedding-8B
```

## 8. 本地正式跑
如果只跑现成结果的官方评测：

```bash
python eedi/run_official_eval_with_qwen.py \
  --input_file eedi/outputs/run_20260423_111159/official_eval_input.csv \
  --evaluations sim-text,sim-corr-errs \
  --embedding_api_base_url http://127.0.0.1:8000/v1 \
  --embedding_model Qwen/Qwen3-Embedding-8B \
  --embedding_api_key EMPTY \
  --no-llm_judge_batch_api
```

如果跑整条 EEDI 流水线，就直接用 `run_eedi_experiments.py`，它现在也会把这些参数自动透传到官方评测阶段。

## 9. 这次改动改了什么
1. 改了哪个环节  
改的是 `sim-text` 的 embedding 获取方式。现在既支持原来的本地 `SentenceTransformer`，也支持远程 OpenAI-compatible `/v1/embeddings`。

2. 理论依据是什么  
`cos-sim` 需要的是同一个 embedding 模型产生的向量，并不要求 embedding 必须在本地机上算。把计算移到服务器不会改变指标定义。

3. 如何避免 cheating  
这里只是把 embedding 计算位置从本地改到远端，没有改样本、没有改指标定义、没有改 ground truth、没有把评测信息送回 generation path。
