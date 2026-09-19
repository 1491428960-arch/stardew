# Vertex Billing 付款资料填写与社区案例研究

日期：2026-09-07

研究问题：用户在准备 Vertex AI 前置条件时，需要填写国家/地区、付款人信息和账单地址；应如何填写，社区案例是否支持使用其他国家/地区地址。

研究范围：Google Cloud Billing、Google payments profile、Vertex AI 前置条件，以及公开 Google Developer Forum、Reddit 搜索摘要和 Stack Overflow 案例。

排除项：不登录用户账号、不提交付款资料、不读取银行卡或身份证信息、不推荐伪造地址、不购买共享账号或共享 Cloud project。

## 结论

1. 应填写真实的付款主体、真实的账单国家/地区、真实地址，以及与付款工具和可验证文件一致的信息。不能因为网络出口使用日本、美国或台湾节点，就把付款国家/地区填成对应地区。
2. Google 官方说明，一个 payments profile 只能关联一个国家/地区，已有 profile 的国家/地区不能直接修改；如果确实迁居到另一个国家/地区，需要创建新的 country-specific profile。Google Cloud 文档还说明，若要修改 Cloud Billing account 的国家/地区，需要新建 billing account。
3. 社区案例中比较稳定的共同点是：姓名和地址需要与付款资料、银行卡/支付机构记录或后续身份证明材料相互一致；个人账号也可能触发身份验证。社区没有提供可信证据证明“填一个支持地区的朋友地址”能稳定通过并获得 Vertex 资格。
4. 如果用户的真实付款国家/地区在表单中没有可选项，不应随便选择日本、美国、台湾等选项来绕过限制。此时应停止创建，改为联系 Google Billing 支持，或使用用户本人实际拥有、且法律和付款资料均对应支持地区的账号/付款主体。
5. 地址确认弹窗卡住是社区中出现过的界面问题，但没有统一可靠的地址内容修复方案。可先排除浏览器/页面问题；如果仍卡住，应保存错误时间和页面信息，联系官方 Billing 支持，不要反复创建多个错误付款 profile。

## 判断依据

### 来源事实

- Google Cloud Billing 文档把 payments profile 描述为负责支付账单的法律主体，并说明 mailing address 可以包括合法注册的企业地址和账单寄送地址。
- Google Payments 官方帮助明确写明：每个 payments profile 只能关联一个国家/地区，已有 profile 不能更改国家/地区；需要新国家/地区时，应创建新的 country-specific profile，并输入该国家/地区对应的姓名和地址。
- Google Cloud 的货币和支付方式由国家/地区与币种决定；不同国家/地区可用的信用卡、借记卡、银行账户等支付方式不同。
- Google Developer Forum 的公开回复说明，个人 GCP 账号也可能需要验证；如果自动验证失败，应联系 Cloud 支持确认可接受的替代验证方式。

### 社区观察

- 2025 年 Reddit 的 Google Cloud 讨论中，一位用户描述了姓名和地址已经在 payments profile 中验证，但 Cloud 仍要求提交身份证明和包含姓名、地址的 utility bill；这说明“地址已填入”不等于“后续永远不需要验证”。该帖只是用户案例，不是官方规则。
- 2025 年 Reddit 的另一个 Google Cloud 讨论中，用户报告上传信用卡和政府身份证明后多次被拒；回答者推测实体银行信用卡比虚拟卡/借记卡更容易通过，但这只是社区回答，Google 官方页面没有作出“必须实体信用卡、一定拒绝借记卡”的统一保证，不能当作硬规则。
- 2025—2026 年 Google Developer Forum 的多条帖子报告在地址建议确认弹窗点击 Confirm 后没有反应。这些帖子没有证明改成某个国家或伪造地址可以解决问题。
- Google Developer Forum 的“Change country”帖子及官方文档均指向同一结论：Cloud Billing country 设置后不能直接改，错误时联系 Billing 支持或建立新的正确 billing account。
- 较早的 Stack Overflow 中国地区案例报告当时无法选择 China；该案例与 Google Maps、旧政策和旧时间点有关，只能作为历史背景，不能单独作为 2026 年 Vertex AI 的现行政策证据。

### 本次直接核对的社区帖子

- Google Developer Forum 的 [Change country](https://discuss.google.dev/t/change-country/102331) 帖子中，用户误选国家后询问如何修改；Google Cloud 前员工的公开回复是：Billing account 建立后不能修改 billing country，应联系 Billing support。该帖没有提供“改填某个外国地址”的办法。
- Google Developer Forum 的 [Being an Indian individual, how can i setup and verify billing GCP account?](https://discuss.google.dev/t/being-an-indian-individual-how-can-i-setup-and-verify-billing-gcp-account/173113/2) 帖子中，个人用户即使不是组织，也可能被要求地址证明或其他验证材料；回复建议联系 Cloud support，确认个人账号可接受的替代验证方式。它说明“选 Individual”不等于免验证。
- Google Developer Forum 的 [Billing account update won't save address](https://discuss.google.dev/t/billing-account-update-wont-save-address/298810) 帖子中，用户填写地址后在建议地址弹窗点击 Confirm 没有反应，无法创建 Billing account；截至本次核对没有看到可复用的地址内容或替代国家填法。
- 搜索到的 Reddit `r/googlecloud` 中国学生案例，讨论的是没有可用虚拟卡、无法注册 Billing 以及“能否在中国使用 Vertex AI”；搜索摘要没有显示经过验证的地址填写方案。Reddit 页面本身受访问限制，因此只能作为未验证的社区线索，不能把它写成成功案例。

直接核对后的判断是：社区能确认的是资料一致、必要时联系官方 Billing support，以及处理页面故障；没有可靠社区证据证明“大陆用户把 Country 填成美国、日本、台湾或新加坡，再配一个当地地址”可以稳定开通 Vertex AI。所谓“这样填就过”的帖子，即使有人短期成功，也无法证明账号符合 Google 的付款与服务资格，且存在后续身份/地址审核失败的风险。

### 找到的社区完整流程教程

目前最接近用户当前界面的完整帖子是 Google Developer Forum 的 [Stuck in Vertex AI Studio Express — Cannot Access Google Cloud Console](https://discuss.google.dev/t/stuck-in-vertex-ai-studio-express-cannot-access-google-cloud-console/191407)。帖子中的社区成员 leoy 给出了一套带截图的 Express Mode 升级流程：

1. 打开 `https://console.cloud.google.com/vertex-ai/studio/overview`，点击 `Upgrade account`。
2. 在打开的页面绑定付款 profile，并点击 `Enable billing`。
3. 等待页面完成升级，看到状态变化后点击 `Close`。
4. 打开 `https://console.cloud.google.com/api-sandbox/billing/details`。
5. 在右侧 `Access all Google Cloud` 区域点击 `Learn more and get started`，再点击 `Continue`。
6. 升级完成后再次点击 `Continue` 刷新页面，验证是否已经能访问完整 Cloud Console。

该帖后续用户反馈，经过 Google 团队处理后，Billing 绑定步骤被跳过，最终成功获得完整 Cloud Console；但这不是普通用户可自行复制的地址填写技巧。该帖在 2026-03-21 又有一名明确自称在中国的用户跟帖，指出自己的 Billing 国家列表中没有 China；截至本次核对，该跟帖没有得到可验证的中国地区解决方案。

因此，这套教程可以作为“界面流程教程”，但不能作为“中国大陆没有 Country 选项时的绕过教程”。它的前置条件仍是账号能够建立合法、可验证的付款 profile；在 Country 列表没有真实付款国家时，应停在第 2 步并联系 Billing support。

## 逐字段建议

| 表单字段 | 个人账号的建议填写 | 不要这样填 |
|---|---|---|
| Account type | 个人就选 Individual；只有真实注册企业且付款主体是企业时才选 Business | 不要为了通过验证把个人伪装成企业 |
| Country/Region | 选择真实居住地和付款主体所在国家/地区，并与付款 profile、付款工具和证明材料一致 | 不要按 VPN/代理出口选择日本、美国、台湾等地区 |
| Legal name / Name | 使用本人真实姓名；尽量与付款 profile、银行卡持有人和身份证明一致 | 不要填朋友、卖家或共享账号持有人姓名 |
| Address line | 填真实账单地址；个人填写实际居住/可验证地址，企业填写合法注册地址 | 不要填酒店、虚拟办公室、代理节点所在地或随机地址 |
| City / State / Postal code | 按该真实地址的官方行政区划和邮编填写；如果页面只接受拉丁字母，可使用同一地址的官方/银行可识别转写 | 不要为了匹配外国模板编造城市、州或邮编 |
| Payment method | 使用本人名下、允许国际线上和周期性扣款的付款工具 | 不要使用共享卡、购买的卡、来源不明的虚拟卡或他人支付资料 |
| Currency | 接受由付款国家/地区和 billing profile 决定的币种 | 不要为了便宜或绕过地区手动挑选不对应的币种 |
| Phone / email | 使用本人可接收验证信息的联系方式，并与 Google payments profile 保持一致 | 不要使用卖家、临时号码或无法接收验证的联系方式 |

以上“真实地址、姓名、付款工具相互一致”是合规填写建议；社区关于实体信用卡更容易通过的内容仅为经验，不应被理解为官方保证。

## 用户实际操作建议

1. 如果当前表单中的国家/地区有你的真实付款国家/地区：选择真实国家，按真实资料填写，不要根据代理线路改变选择。
2. 如果真实国家/地区没有可选项：不要继续提交，不要尝试日本、美国、台湾等替代地址；记录页面显示的可选国家和错误信息，联系 Google Cloud Billing 支持。
3. 如果国家已经选错但付款 profile 还没有提交：返回修改后再继续。
4. 如果 payments profile 或 Cloud Billing account 已经创建：不要反复编辑国家；先查看官方提示，必要时创建新的正确 profile/billing account，或先联系 Billing 支持。
5. 如果地址确认弹窗卡住：只做低风险排查，例如使用最新 Chrome/Edge、无痕窗口、关闭会拦截页面脚本的扩展、重新登录并确认页面国家与地址一致；不要修改系统代理、注册表或浏览器全局设置。
6. 如果出现身份证、地址证明或银行卡验证：只上传 Google 页面明确要求的本人材料，并确认姓名和地址一致；不要把材料发给我或第三方。
7. Billing 创建成功后，再准备 ADC 和 Vertex API；Billing profile 成功本身仍不等于 `gemini-3.7-flash` 最小请求成功。

## 与当前项目的关系

当前项目只能在工作树内适配 Vertex Provider，不能替用户创建 Cloud project、开通 billing、提交身份证明或代填付款资料。账号侧完成后，Bridge 会使用项目配置中的 project/location，并通过 ADC 获取短期 access token；不会把银行卡信息、付款地址证明或 access token 写入项目。

后续真实验收仍必须是一次最小 Vertex 请求，至少同时满足：

```text
HTTP 成功
provider=vertex
fallback=false
非空回复
choices[0].message.content 可解析
```

`/health=200`、billing profile 创建成功或 ADC 能生成 token，都不能单独证明 Gemini/Vertex 对话请求成功。

## 来源

- [Manage your Cloud Billing account](https://cloud.google.com/billing/docs/how-to/manage-billing-account) —— 账单账户、payments profile、法律主体和 mailing address 的官方说明。
- [Add, remove, or update a payment method](https://cloud.google.com/billing/docs/how-to/payment-methods) —— 支付方式受国家/地区和币种影响的官方说明。
- [Currencies available for Cloud Billing self-serve, auto-pay accounts](https://cloud.google.com/billing/docs/resources/currency) —— 国家/地区、币种和可用支付方式的官方列表。
- [Change countries in your payments profile](https://support.google.com/paymentscenter/answer/9037801?hl=en) —— payments profile 国家/地区不可直接修改的官方说明。
- [Google Developer Forum: Change country](https://discuss.google.dev/t/change-country/102331) —— 社区回复指出 Cloud Billing country 设置后不能直接更改，应联系 Billing 支持。
- [Google Developer Forum: Being an Indian individual, how can I setup and verify billing GCP account?](https://discuss.google.dev/t/being-an-indian-individual-how-can-i-setup-and-verify-billing-gcp-account/173113/2) —— 社区/官方人员回复说明个人账号也可能需要验证。
- [Google Developer Forum: Billing account update won't save address](https://discuss.google.dev/t/billing-account-update-wont-save-address/298810) —— 地址确认弹窗无法继续的社区案例。
- [Reddit: How to verify your payment information to complete the Google Cloud Signup](https://www.reddit.com/r/googlecloud/comments/1jf0nw5/how_to_verify_your_payment_information_to/) —— 用户验证材料与付款工具的经验，非官方规则。
- [Reddit: Profile Verification for Google Cloud Billing Account](https://www.reddit.com/r/googlecloud/comments/1i09a85/profile_verification_for_google_cloud_billing/) —— 姓名、地址、身份证明和 utility bill 的用户案例，非官方规则。
- [Reddit: Google Cloud billing set-up keeps freezing on the address confirmation pop-up](https://www.reddit.com/r/googlecloud/comments/1q41ilt/google_cloud_billing_setup_keeps_freezing_on_the/) —— 地址确认界面卡住的用户案例，未形成统一解决方案。
- [Stack Overflow: google cloud platform billing account china](https://stackoverflow.com/questions/55114341/google-cloud-platform-billing-account-china) —— 较早的中国地区历史案例，仅作背景，不作为当前 Vertex 政策依据。

## 限制

- Google Cloud 控制台的具体字段、支持国家、审核材料和支付方式会随账号类型、国家/地区、产品和时间变化；本报告没有登录用户账号验证当前表单。
- Reddit 页面受访问限制，本次对 Reddit 内容使用公开搜索结果摘要核对，未将摘要当作官方事实；相关内容只作为社区经验，并明确标注为非官方。
- 没有执行付款、创建 Cloud project、启用 billing、提交身份证明或真实 Vertex 请求。
- 本报告不判断用户个人是否具备某个国家/地区的合法居住权、付款资格或税务资格；这只能由用户本人和 Google Billing 根据真实资料判断。
