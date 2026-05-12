from vllm import LLM, SamplingParams
import config

# ========================
# 初始化 vLLM 模型（已修复）
# ========================
def init_vllm():
    llm = LLM(
        model=config.MODEL_PATH,
        tensor_parallel_size=config.TENSOR_PARALLEL_SIZE,
        gpu_memory_utilization=config.GPU_MEMORY_UTILIZATION,
        dtype=config.DTYPE,
        max_model_len=config.MAX_MODEL_LEN,
        trust_remote_code=True,
        # 已删除错误参数 device="cuda"
    )

    sampling_params = SamplingParams(
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
        top_p=config.TOP_P,
        presence_penalty=config.PRESENCE_PENALTY,
        frequency_penalty=config.FREQUENCY_PENALTY,
        stop=["<|endoftext|>", "<|im_end|>", "<|im_start|>"]
    )
    return llm, sampling_params

# ========================
# 推理函数
# ========================
def generate_answer(llm, sampling_params, prompt):
    outputs = llm.generate(prompt, sampling_params)
    return outputs[0].outputs[0].text.strip()

# ========================
# 测试
# ========================
if __name__ == "__main__":
    llm, sampling_params = init_vllm()

    test_prompt = "2**31-1="
    answer = generate_answer(llm, sampling_params, test_prompt)
    print("模型回答：", answer)