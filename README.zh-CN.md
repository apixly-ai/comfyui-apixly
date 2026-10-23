<picture>
  <source media="(max-width: 640px)" srcset="assets/hero-mobile.svg">
  <img src="assets/hero.svg" alt="Apixly ComfyUI：15 个节点、12 个入门工作流，账号绑定、生图、参考编辑、生视频及免费创作工具。" width="1440">
</picture>

# Apixly Media for ComfyUI

**15 个节点 · 12 个工作流 · 9 个免费工具节点 · [English](README.md)**

在 ComfyUI 中使用 [apixly.ai](https://apixly.ai) 生图、参考图编辑和生视频。连接自己的 Apixly 账号，选择默认 Studixly Key 或自己已有的 Key，懒加载该 Key 当前可用的图片/视频模型。账号、额度、API Key 与用量由 [platform.apixly.ai](https://platform.apixly.ai) 统一管理。

插件免费；模型生成按你的 Apixly 账号余额计费。模型目录代表可发现的权限，不代表每个模型/参数都已完成质量验收。当前价格以[模型页面](https://platform.apixly.ai/models)为准。

## 安装和连接

从 [Comfy Registry](https://registry.comfy.org/publishers/apixly/nodes/comfyui-apixly) 安装，或把仓库克隆到 `ComfyUI/custom_nodes/comfyui-apixly`，在实际 ComfyUI Python 环境安装 `requirements.txt` 后重启。详细命令见[英文安装说明](README.md#install)。

打开 **Apixly 侧栏 → Connect**。点击时会先准备一个浏览器标签，再跳转到 Apixly 的正常登录/授权页；登录后审核并确认 Key。若未自动打开，使用 **Open authorization page** 跳转，或 **Copy authorization link** 手动打开。同一个有效授权流程会继续等待，不需要再次创建验证码。在同一授权链接打开的确认页，可填写或核对插件显示的短认证码；该链接包含本次授权流程的地址。

凭据保留在 ComfyUI 服务端，不写进节点或工作流。也支持服务端环境变量 `APIXLY_API_KEY`，两种模式需显式切换。共享服务实例的用户可能使用同一个已绑定 Key；不同账号应使用隔离实例。完整边界见 [PRIVACY.md](PRIVACY.md)。

## 这次迁入的网页工具

五个新节点覆盖四项功能，均可离线执行，不读取 Key、不访问网络、不调用模型。加上原有四个免费提示词节点，共九个免费节点。提示词工具默认 Off；角色计划默认未选择镜头。

四个新模板以 1:1 初始视图聚焦主工具，节点默认宽 300px；详情可竖向滚动，其他节点保留在画布上供平移查看。原版 Templates 会自动缩放整张图，因此仅对带专属标记且初始视图未被改存的模板，在加载后恢复一次初始视图。保存的自定义视图、后续缩放与手动节点尺寸会保留；等待恢复时遇到点击或滚轮操作会取消恢复。旧工作流不受影响。

| 新节点 | 功能和输出 |
| --- | --- |
| Apixly Prompt: Expression | 复用原 5×5 表情网格和参数化人脸；输出 `APIXLY_EMOTION_V2` 设置及指令 |
| Apixly Prompt: Compose V2 | 角度→打光→表情→镜头；输出最终提示词和带版本的设置 JSON |
| Apixly Image: Grid Split | 原图像素切块；输出 IMAGE 列表与完整行列/坐标 JSON |
| Apixly Prompt: AI Enhancement | 免费保真增强指令；输出提示词、参数 JSON、画幅和精确模型 ID |
| Apixly Prompt: Character Sheet Plan | 九类角色设定计划；输出计划 JSON、明确选中的单镜提示词/画幅 |

**表情**：上方更激动、下方更平静，左侧更亲近、右侧更疏离；可填写目标人物。中心格或 Off 不注入表情指令。它是提示词引导，实际表情由模型决定。

**Compose V2**：接受原角度、打光、相机节点的 typed 输出，加上新的 `APIXLY_EMOTION_V2`。原 V1 编译契约和节点保持不变；表情关闭或中性时，V2 最终提示词与 V1 逐字节相同。修改旧工具后，点击 **Refresh preview** 或执行免费 Compose V2，确认当前连接输入。

**网格切分**：Off 将整个原 IMAGE batch 作为一个列表项通传；On 才按“输入 batch→行→列”切分。支持 RGB/RGBA、多张输入及不等尺寸切块，不插值、不填充、不丢边缘。均分采用 floor 边界，自定义 0～1 切线采用正数半入取整；重复/像素重合/空块或总数超过 144 会明确报错。预览按切线比例绘制，执行后读取真实像素坐标。IMAGE 列表会让下游按块执行，通常应接 Preview/Save；若连接付费节点，可能产生多笔请求。

**AI 增强**：复用网页原保真指令和已知模型参数映射。源图连接后自动取实际尺寸，未连接则使用宽高设置；将同源的 model、prompt、parameters_json 和源图显式接入 Image Edit。它属于 **AI 重绘增强**，可能改变细节或文字，不承诺像素不变、真实超分或一定改善。增强模板的付费节点默认 **Mode: Never**，nonce 固定为 0；审核模型与价格后，显式解除静音并只按 Run 一次。保留原 nonce/任务用于恢复。

**角色计划**：包含定妆、转身、头部、表情、动作、服装、色彩材质、比例和 Seedance 参考包。Seedance 包是正面、四分之三、侧面 **三张独立图的计划**。只有主动选择的一个镜头会输出普通 STRING；不会返回自动映射的提示词列表或暗中批量付费。重排设定类型会保留同一镜头身份；移除该镜头则清空选择，必须重新选。原生 `shot_index` 也可手动选择，`-1` 表示未选择。用户文字中的美元符号及模板样式花括号按字面保留，不递归展开。生成后是否角色一致仍须看实际模型结果。

## 12 个入门工作流

在 Templates → comfyui-apixly 打开，或拖入 JSON：

| 工作流 | 用途 |
| --- | --- |
| [原免费创作提示词](example_workflows/creative-prompt.json) | 原角度、打光、相机、Compose |
| [表情与 Compose V2](example_workflows/expression-prompt-v2.json) | 四组创作工具；默认全 Off |
| [原图网格切分](example_workflows/image-grid-split.json) | 选择本地图后离线切分/预览 |
| [AI 增强指令](example_workflows/image-enhancement-prompt.json) | 免费预览；付费编辑默认 Never |
| [角色设定计划](example_workflows/character-sheet-plan.json) | 明确选择一个镜头；无付费节点 |
| [创作→生图](example_workflows/creative-image-generation.json) | 免费编排后显式启用生成 |
| [创作→参考编辑](example_workflows/creative-reference-edit.json) | 免费编排后显式启用参考编辑 |
| [创作→视频](example_workflows/creative-video-generation.json) | 免费编排后显式启用视频 |
| [基础生图](example_workflows/image-generation.json) | 异步任务与图片预览 |
| [基础参考编辑](example_workflows/reference-image-edit.json) | 本地参考图→编辑→预览 |
| [基础视频](example_workflows/video-generation.json) | 提交/查询/下载视频 |
| [参考图→视频](example_workflows/reference-image-to-video.json) | 两个明确付费步骤，保留任务恢复 |

另有六个媒体节点：Image Submit、Image Edit、Image Result、Video Submit、Task Status、Video Result。已验证的既有媒体样例、操作与范围见[英文说明](README.md#see-it-in-comfyui)。图片临时结果会过期，应及时 Save Image；任务未知状态应查询同一任务，不能重复提交。普通参考编辑与原生蒙版重绘不同；当前未开放蒙版重绘。

## 开发验证

安装测试依赖 `python -m pip install -e '.[test]'`，再执行 `python -m pytest -q` 与 `node --test tests/*.test.mjs`。测试 extra 包含 NumPy，运行环境使用宿主 ComfyUI 已有的 PyTorch/NumPy/Pillow。原网页 381e TypeScript 差分 fixture 保留来源哈希；字面插值修复使用单独回归 fixture，未伪造为旧网页输出。

本地/夹具测试只验证编排、参数、像素切片与交互规则；新增功能的原版宿主与真实模型效果须独立验收。支持：[support@apixly.ai](mailto:support@apixly.ai) · [API 文档](https://apixly.ai/docs) · [账号与用量](https://platform.apixly.ai)。
