# EEDI 弱模型 Harness v5 设计说明（2026-05-10）

## 1. 为什么要做 v5

v4 的核心问题不是“弱模型不行”，而是：

> 强模型已经开始决定这轮具体该说什么，甚至在局部上接近决定“该怎么错”。

这样虽然形式上还是“强编译 + 弱实现”，
但本质上已经重新靠回强版 harness：

- 强模型负责当前轮结果走向；
- 弱模型只负责把这条结果说出来。

这和我们想做的“利用弱模型本来就不会做题”不是一回事。

所以 v5 的目标很明确：

> 强模型只负责判断**当前教学支持打开了什么学习机会**，不负责预写这轮答案脚本；弱模型自己在这个机会边界里回应。

---

## 2. 理论依据

v5 不是工程补丁，而是基于下面几类理论。

### 2.1 Assessment Triangle

核心思想是把：

- 学生状态
- 任务观察
- 结果解释

三者分开。

对应我们这里就是：

- `StudentModel / LearningAccessState`：学生当前处在什么边界；
- `TutorTurnProfile / VisibleContext`：当前轮任务和教学输入是什么；
- `PosthocErrorInterpretation`：生成后再解释这句回复体现了什么错误或理解。

参考：

- National Academies, *Knowing What Students Know*  
  <https://nap.nationalacademies.org/catalog/10019/knowing-what-students-know-the-science-and-design-of-educational>

### 2.2 Dynamic Assessment / ZPD

核心不是只看“学生已经会什么”，
而是看：

> 在当前帮助下，学生这一步最多能推进到哪里。

所以 v5 的中间层不再是：

- 这轮该答对还是答错

而是：

- 当前 tutor 这句话之后，学生现在**独立能做什么**
- **借当前支持能做什么**
- **仍然做不到什么**

参考：

- Dynamic Assessment overview  
  <https://www.cambridge.org/core/books/cambridge-handbook-of-culturalhistorical-psychology/dynamic-assessment-in-search-of-its-identity/7FD4BABEE334769480BE6EEF93275567>

### 2.3 Contingent Scaffolding

支架不是替学生把题做完，
而是根据学生当前状态，只降低当前这一步的认知负担。

所以 v5 允许的是：

- 打开局部可见性
- 打开局部尝试机会
- 打开局部澄清机会

不允许的是：

- 预写错答
- 预写正确 claim
- 预写 wrong claim seed

参考：

- Wood, Bruner, Ross, *The role of tutoring in problem solving*  
  <https://doi.org/10.1111/j.1467-8624.1976.tb00381.x>

### 2.4 ECD / ECD for Learning

ECD 的关键是把：

- student model
- task model
- evidence / interpretation

拆开；在学习场景里，还要显式加入 pedagogical layer。

v5 正是在 student model 和 surface generation 中间加了一层：

> `LearningOpportunityState`

它代表的不是“答案”，而是“教学后当前可达的机会结构”。

参考：

- ETS, *Evidence-Centered Design for Assessment*  
  <https://www.ets.org/research/policy_research_reports/publications/chapter/2016/jwau.html>
- ETS, *Evidence-Centered Design for Learning and Assessment Systems*  
  <https://www.ets.org/research/policy_research_reports/publications/report/2011/imbu.html>

### 2.5 Productive Failure

学习者不一定一开始就会；
重要的是让他在有限支持下自然暴露局部理解、局部犹豫、局部错误。

这进一步支持：

> 不要在 generation path 里提前把“这轮该错什么”写死。

参考：

- Kapur, *Productive Failure in Learning Math*  
  <https://www.sciencedirect.com/science/article/pii/S0732312321000535>

---

## 3. v5 的核心边界

一句话：

> 强模型管“机会结构”，弱模型管“当前轮自然回应”。

具体地说：

### 3.1 强模型可以决定什么

- 当前 tutor 这轮在教什么
- 当前学生处在什么学习边界
- 当前支持打开了哪些局部动作
- 当前还不能做哪些动作
- 当前最多能解释到多深
- 当前允许的 response space 和格式边界

### 3.2 强模型不能决定什么

- 这轮具体该答对还是答错
- 这轮具体该犯哪一类错误
- 这轮具体该说哪一句错话
- wrong claim seed
- support-consistent claim seed

### 3.3 弱模型负责什么

- 读取真实上下文和 tutor 当前话语
- 读取第三人称机会边界
- 在这个边界内自然回应
- 允许局部尝试、局部不确定、局部澄清

---

## 4. v5 pipeline

### Step 1：`VisibleContext`

输入：

- 当前轮之前的真实可见历史
- 当前 tutor 这一轮
- 题目和 subject 元数据

作用：

- 保证无未来信息泄漏

### Step 2：`StudentModel / StudentPrior`

作用：

- 给出学生稳定画像
- 但不预判这轮答案

### Step 3：`TutorTurnProfile / TutorMove`

作用：

- 判断 tutor 这轮的教学动作是什么

### Step 4：`LearningAccessState`

作用：

- 判断当前学生在 tutor 当前支持下的可达边界

### Step 5：`SupportUptake`

作用：

- 判断学生这轮可能怎样接住 tutor 这次支持

### Step 6：`MathClaimAffordance + MediatedTargetAvailability + TurnResponseConstraint`

作用：

- 把“当前轮是否该产生局部 claim、当前局部目标是否可见、当前回应空间是什么”收束出来

### Step 7：`LearningOpportunityState`

这是 v5 新核心对象。

它只回答：

- 学生现在独立能做什么
- 借当前支持能做什么
- 仍然做不到什么
- 当前局部困惑轴是什么
- 当前最多能解释到多深

它不回答：

- 这轮具体答案是什么
- 这轮具体错在哪里

### Step 8：`OpportunityConstraintBundle`

把机会状态翻译成弱模型可执行边界：

- 当前局部焦点
- response space
- claim requirement
- 句数限制
- 可做动作
- 不可做动作
- 支持使用规则

但仍然不放：

- wrong claim seed
- support claim seed
- 预写答案 kernel

### Step 9：弱模型生成 `StudentTurn`

弱模型在机会边界里自然生成当前 student turn。

### Step 10：事后解释

生成完成后，再做：

- `local_error_state_for_analysis`
- `strong_error_blueprint`
- detached eval

这一步和 generation path 严格隔离。

---

## 5. 新增对象

### 5.1 `LearningOpportunityState`

字段：

- `independently_available_acts`
- `support_enabled_acts`
- `still_unavailable_acts`
- `salient_confusion_axes`
- `response_space`
- `required_local_focus`
- `max_explanatory_depth`

### 5.2 `OpportunityConstraintBundle`

它兼容现有 runner 输出结构，
同时新增：

- `independently_available_acts`
- `support_enabled_acts`
- `still_unavailable_acts`
- `salient_confusion_axes`
- `claim_permission`
- `max_explanatory_depth`
- `tutor_support_visibility`

---

## 6. 与 v4 的根本差异

### v4

- 强模型先写局部内容 kernel
- 弱模型只做表层 realization

### v5

- 强模型只写机会结构
- 弱模型自己决定这轮具体怎么回应

所以：

> v4 是“强模型规划内容，弱模型说出来”；  
> v5 是“强模型规划边界，弱模型自己作答”。

---

## 7. 当前实现边界

这次实现先做到：

1. 新增 `v5` 对象层和 prompt；
2. 让 `run_eedi_weak_harness.py` 支持 `--architecture_version v5`；
3. 让 `local_error_state` 退出 v5 的 generation path；
4. 保留它在生成后的事后分析角色；
5. 增加 `tests_smoke_weak_harness_v5.py`。

这次还没做的是：

1. 全量 v5 实验；
2. v5 指标与强版 / v3 / v4 的正式对比；
3. 更细的 response-space 专项校验；
4. 更正式的 posthoc 机会-错误映射分析。

---

## 8. 一句话总结

v5 的真正核心不是：

> 用弱模型去执行强模型写好的答案脚本。

而是：

> 让强模型只判断当前支持打开了什么学习机会，再让弱模型自己在这个机会边界里回应。

也就是：

> 强模型负责“这一步能看到什么”，弱模型负责“在只看到这些的情况下会怎么说”。
