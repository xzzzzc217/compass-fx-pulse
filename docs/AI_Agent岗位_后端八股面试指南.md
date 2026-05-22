# AI Agent 岗位｜后端八股面试指南（含 CompassFXPulse 项目落地）

> **写给谁**：投蚂蚁 / 字节 / 阿里 / 腾讯 **AI 应用工程 / Agent 工程 / LLM Infra** 岗位，但出身偏 ML / 算法、后端八股不扎实的同学。
>
> **本指南和经典 Java 八股的区别**：
> - 不堆 50 个名词、不给"30s 话术"——每题用 **300-500 字深答**，能在面试讲 3-5 分钟。
> - 每题都用我们 **CompassFXPulse 项目**做锚点举例：`backend/app/` 里某个文件、某段实现、某个数字。
> - 优先讲 **AI Agent 岗位真正问到的**——缓存、异步、连接池、限流、Streaming、可观测——把 Java GC 这种 Python 后端不太相关的话题放后面。
> - 凡是有"业内争议"的话题（Redlock 安不安全、连接池大小怎么定）会**正反面都讲**，避免给出错误一家之言。
>
> **怎么读**：
> - 一遍**通读**做 mental model（半天）
> - 二遍**对着项目代码读**（`backend/app/cache.py` / `db.py` / `rate_limit.py` / `routes_async.py` 等）
> - 三遍**口播练习**——每题对着空气讲 3 分钟，卡壳的回来复习
>
> **项目背景速回顾**（每个话题都会回引用）：
> - 后端：Flask 8080（sync, WSGI）+ FastAPI 8082（async, ASGI 并行部署）
> - 数据：MySQL（17K 行汇率 + 900 行预测）+ ChromaDB（251 chunks）
> - 缓存：`app/cache.py` 双后端（TTLCache 默认 / Redis 可选）
> - 限流：`app/rate_limit.py` token bucket per-IP
> - LLM 路由：DeepSeek 云端（Agent 决策）+ Qwen3-1.7B-LoRA 本地（聊天）
> - Phase 4 数字：缓存 6500× 提速、QPS 5→350+、注入防御 96.8%、评测 pass 93.5%

---

## 目录

```
第 0 部分 · AI Agent 岗位的后端八股优先级矩阵

第 1 部分 · 数据存储与查询（5 题）
  1.1  数据库索引深解（B+ 树 / 聚簇 / 最左前缀 / EXPLAIN）
  1.2  事务隔离级别 + MVCC + 锁
  1.3  慢查询定位的完整工作流
  1.4  ORM vs raw SQL（Python 后端选型）
  1.5  连接池设计与调参

第 2 部分 · 缓存设计（6 题，AI 岗位必考）
  2.1  Cache 三类问题（击穿 / 雪崩 / 穿透）完整解决
  2.2  Cache 4 种读写模式
  2.3  Redis 5 基本数据结构与底层
  2.4  Redis 持久化（RDB / AOF / 混合）
  2.5  Redis 高可用（主从 / 哨兵 / 集群）
  2.6  多级缓存设计 + Bloom Filter 应用

第 3 部分 · 并发与异步（7 题，AI 岗位必考）
  3.1  线程池 7 参数 + 调参方法论
  3.2  Python GIL + asyncio 事件循环深解
  3.3  协程 vs 线程 vs 进程
  3.4  同步原语家族（锁 / 信号量 / 读写锁 / CAS）
  3.5  分布式锁（Redis SETNX / Redlock / Zookeeper / etcd）
  3.6  幂等性设计模式（重试场景必懂）
  3.7  限流算法（Token Bucket / Leaky Bucket / Sliding Window）

第 4 部分 · 网络与协议（5 题）
  4.1  TCP 三 / 四次握手 + TIME_WAIT 优化
  4.2  HTTP/1.1 → HTTP/2 → HTTP/3
  4.3  HTTPS 完整握手 + TLS 1.3
  4.4  WebSocket / SSE / 长轮询对比（Streaming 必考）
  4.5  反向代理与负载均衡算法

第 5 部分 · 消息队列与异步管道（3 题）
  5.1  Kafka 高吞吐 4 大原因
  5.2  消息可靠性的 3 段防护
  5.3  AI Agent 场景的 MQ 应用

第 6 部分 · 架构设计与模式（4 题）
  6.1  5 种最常考的设计模式 + 项目对应
  6.2  熔断 / 降级 / 重试三件套
  6.3  分布式事务（2PC / TCC / Saga / 事务消息）
  6.4  CAP / BASE / 一致性算法

第 7 部分 · AI Agent 岗位特有议题（5 题，差异化加分）
  7.1  LLM API 配额与限流
  7.2  长任务管理（checkpoint + 断点续跑）
  7.3  Streaming 后端架构
  7.4  Multi-tenancy 隔离
  7.5  LLM 成本可观测

第 8 部分 · Java 补充（面 Java 岗用，~3 题，可选读）
  8.1  volatile / synchronized / Lock / AQS
  8.2  JVM 内存模型与 GC
  8.3  ConcurrentHashMap 演进
```

---

# 第 0 部分 · AI Agent 岗位的后端八股优先级矩阵

不是所有后端八股对 AI Agent 岗位都一样重要。下表是面经统计结果（蚂蚁/字节/阿里 2026 春招约 30 份截图）：

| 话题 | AI Agent 出现频率 | 普通后端出现频率 | 优先级 |
|---|---|---|---|
| 缓存三类问题（击穿/雪崩/穿透） | **80%** | 70% | ⭐⭐⭐⭐⭐ |
| asyncio / 事件循环 / GIL | **75%** | 30% | ⭐⭐⭐⭐⭐ |
| 限流算法 | **65%** | 50% | ⭐⭐⭐⭐⭐ |
| Streaming（SSE / WebSocket） | **65%** | 25% | ⭐⭐⭐⭐⭐ |
| 数据库索引 + EXPLAIN | 55% | 90% | ⭐⭐⭐⭐ |
| LLM API 限流 / 配额 / 重试 | **60%** | 0% | ⭐⭐⭐⭐ |
| Redis 数据结构 / 持久化 | 50% | 70% | ⭐⭐⭐⭐ |
| 分布式锁 | 45% | 60% | ⭐⭐⭐⭐ |
| 连接池调参 | 40% | 50% | ⭐⭐⭐⭐ |
| TCP 握手 / TIME_WAIT | 30% | 60% | ⭐⭐⭐ |
| 事务隔离级别 / MVCC | 25% | 80% | ⭐⭐⭐ |
| 消息队列 | 20% | 50% | ⭐⭐⭐ |
| 设计模式 | 30% | 40% | ⭐⭐⭐ |
| JVM GC | **5%** | 60% | ⭐⭐ |
| volatile / AQS | **5%** | 50% | ⭐⭐ |

**结论**：对 AI Agent 岗位，**先吃透第 2 / 3 / 4 / 7 部分**——缓存 / 并发 / 网络 / AI 专题。**Java 八股放最后**，Python 出身完全可以诚实说"了解原理，没深入"。

---

# 第 1 部分｜数据存储与查询

## 1.1 数据库索引深解：B+ 树 / 聚簇 / 最左前缀 / EXPLAIN 全流程

**面经原题**：
- "数据库索引怎么设计的？为什么用 B+ 树不用别的？"（字节后端、蚂蚁后端高频）
- "InnoDB 的索引和 MyISAM 的索引区别是什么？"
- "你怎么定位慢查询？" / "EXPLAIN 输出里 `type` 字段什么意思？"

### 一、项目场景：我们 historicaldata 表上的索引设计

我们 MySQL `historicaldata` 表存 17K+ 行汇率数据，结构：

```sql
CREATE TABLE historicaldata (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,         -- 聚簇索引
    currencytype1 VARCHAR(3),                     -- e.g. "USD"
    currencytype2 VARCHAR(3),                     -- e.g. "JPY"
    time DATETIME,                                -- 日期
    rate DECIMAL(10,5),                           -- 汇率
    INDEX idx_pair_time (currencytype1, currencytype2, time)
) ENGINE=InnoDB;
```

最热查询是 `backend/app/agent/tools.py:_get_exchange_rate()` 用的：
```sql
SELECT time, rate FROM historicaldata
WHERE currencytype1='USD' AND currencytype2='JPY'
ORDER BY time DESC LIMIT 1
```

**这个 query 怎么用上 `idx_pair_time` 联合索引**——讲明白这一题 = 把整个索引体系讲透。

### 二、为什么 B+ 树，不是哈希 / 红黑树 / B 树

数据库索引的本质需求**3 个**：
1. **快速点查**：`WHERE id=42` 要 < 1ms
2. **范围查询**：`WHERE time BETWEEN ...` 要顺扫
3. **海量数据下磁盘 IO 少**：表 10 亿行索引也得装得下且查得快

候选数据结构对比：

| 结构 | 点查 | 范围 | 磁盘 IO（10 亿行） | 致命缺点 |
|---|---|---|---|---|
| **哈希表** | O(1) | **不支持** | 1 次 | 范围查询全表扫——`WHERE time > X` 直接报废 |
| **红黑树（AVL）** | O(log₂ N) | OK | log₂(10⁹) = **30 次 IO** | 树太"瘦高"，磁盘 IO 太多 |
| **B 树** | O(log_M N) | 还行（要回溯） | log₁₀₀(10⁹) = **5 次 IO** | 叶子节点不连续，范围查要回到父节点 |
| **B+ 树** ✅ | O(log_M N) | **极好**（叶子链表） | **3-4 次 IO** | — |

**B+ 树 vs B 树两个核心改进**（必背）：

1. **非叶子节点只存 key 不存 data**：每个 16KB page 能装 ~1000 个 key + 子节点指针，**fanout（分叉数）巨大**，树更矮。**3 层 B+ 树 = 1000³ ≈ 10 亿条记录 = 3 次磁盘 IO**——这就是为什么"3 层 B+ 树撑住 10 亿数据"是面试金句。
2. **叶子节点用双向链表横向连起来**：范围查询从最左叶子顺指针走到最右，**不用回溯父节点**——磁盘顺序读，SSD 也比随机读快 10×。

**B+ 树高度的数学**（强烈建议背）：
- InnoDB page size = 16KB
- 非叶子节点每个 entry = key（约 8 字节）+ 子节点指针（6 字节）≈ 14 字节
- 一个非叶子 page 装 16384 / 14 ≈ **1170 个 entry**
- 叶子节点每个 entry = 一行数据（假设 100 字节）
- 一个叶子 page 装 16384 / 100 ≈ **160 行**
- 3 层 B+ 树 = 1170 × 1170 × 160 ≈ **2.2 亿行**
- 4 层 B+ 树 = 1170³ × 160 ≈ **2500 亿行**
- → **生产中 B+ 树永远不会超过 4 层**，4 次磁盘 IO 封顶

### 三、聚簇索引 vs 非聚簇索引——InnoDB 的核心设计

这是 InnoDB（MySQL 默认引擎）和 MyISAM 最大的差别。

**聚簇索引（clustered index）**：
- B+ 树**叶子节点直接存整行数据**
- InnoDB 的**主键索引就是聚簇索引**
- 一张表**只能有一个聚簇索引**（因为整行数据只能"按一个顺序"物理存）
- 查询：`WHERE id=42` → 1 次 B+ 树查找 → 拿到整行 ✅

**非聚簇索引（secondary index / non-clustered）**：
- 叶子节点存的是**主键值**（不是整行数据）
- 一张表可以有 N 个非聚簇索引
- 查询：`WHERE name='Alice'`（name 是非聚簇）→ 1 次非聚簇 B+ 树查找拿到主键 → 1 次聚簇 B+ 树查找拿到整行 = **2 次树查找**，叫**回表**

**项目里 historicaldata 的索引布局**：
```
聚簇索引（primary key id）
├── 叶子节点存 整行 (id, ct1, ct2, time, rate)

非聚簇索引 idx_pair_time (ct1, ct2, time)
├── 叶子节点存 (ct1, ct2, time, id)
└── 拿 id 回表 → 聚簇索引拿整行
```

**关键优化：覆盖索引（covering index）**

如果你查 `SELECT time, rate FROM historicaldata WHERE ct1='USD' AND ct2='JPY' ORDER BY time DESC LIMIT 1`，并且把 rate 也加进联合索引：

```sql
INDEX idx_pair_time_rate (ct1, ct2, time, rate)
```

那么 `time, rate` 在非聚簇索引叶子节点就有了——**不用回表**，1 次树查找搞定。**EXPLAIN 的 `Extra` 列会显示 `Using index`** 表示用了覆盖索引。

我们项目当前没用覆盖索引（rate 没加进 idx）。**生产化改进点**：把高频字段加进索引，省一次 IO。

### 四、最左前缀原则——联合索引的关键

联合索引 `(a, b, c)` 在 B+ 树里**按 (a, b, c) 字典序**排列。查询能用上索引的条件：

| WHERE 条件 | 用上索引？ | 原因 |
|---|---|---|
| `a=?` | ✅ | 最左前缀命中 |
| `a=? AND b=?` | ✅ | 前 2 列 |
| `a=? AND b=? AND c=?` | ✅ | 全命中 |
| `a=? AND c=?` | ⚠️ 部分 | a 用上，c 跳过 b 用不上 |
| `a>? AND b=?` | ⚠️ 部分 | a 用上但范围查后 b 就没法用了 |
| `b=? AND c=?` | ❌ | 缺最左 a，全表扫 |
| `a=? ORDER BY b` | ✅ | 字典序天然有序，ORDER BY 免排序 |

**项目里**：索引 `(currencytype1, currencytype2, time)` 三列顺序怎么定？
- ① **基数高的放前面**（区分度大）——currencytype1 有 6 个币（USD/EUR/GBP/JPY/HKD/AUD），currencytype2 也 6 个，time 是连续值（区分度最高）。
- ② **常一起用的列要顺序对**——我们最高频查 `WHERE ct1=? AND ct2=? ORDER BY time DESC`，所以 (ct1, ct2, time) 顺序正好。
- ③ **range column 放最后**——time 是范围列（DESC、BETWEEN），放最后能享受 B+ 树叶子顺序扫优势。

### 五、EXPLAIN 输出怎么读——慢查询定位核心工具

```sql
EXPLAIN SELECT time, rate FROM historicaldata
WHERE currencytype1='USD' AND currencytype2='JPY'
ORDER BY time DESC LIMIT 1;
```

关键列：

| 列 | 含义 | 怎么看好坏 |
|---|---|---|
| **type** | 访问类型 | `const` > `eq_ref` > `ref` > `range` > `index` > **`ALL`（全表扫，坏）** |
| **key** | 实际用的索引 | 应该是 `idx_pair_time`；如果是 `NULL` 说明没用索引 |
| **key_len** | 索引使用了几列字节 | 联合索引 (varchar(3)*2 + datetime) ≈ 12 字节，越大说明用上的列越多 |
| **rows** | 估计扫描行数 | 越小越好；如果 17K 说明全表扫 |
| **Extra** | 额外信息 | `Using index`（覆盖索引✅）/ `Using where`（过滤）/ `Using filesort`（排序未用索引❌）/ `Using temporary`（用了临时表❌） |

我们项目的 query EXPLAIN 应该输出：
```
type=ref, key=idx_pair_time, key_len=12, rows=~30, Extra=Using where; Backward index scan
```

`Backward index scan` 是 MySQL 8 的优化——`ORDER BY time DESC` 不用专门 sort，直接反向走 B+ 树叶子链表。

### 六、生产化最佳实践

1. **主键用 BIGINT auto_increment**，不用 UUID
   - UUID 随机分布会导致 B+ 树**频繁页分裂**，性能差 3-5×
   - 自增主键单调递增，新行总是追加到 B+ 树最右叶子——**几乎没页分裂**
   - 如果业务需要 UUID 当对外 id，**额外存一个字段加索引**，主键还是 auto_increment

2. **索引不是越多越好**
   - 每个索引占空间（10 亿表 + 5 索引 = 索引比数据还大）
   - 每个写操作要更新所有索引（10 索引 = 10 次 B+ 树写）
   - **经验值**：单表索引 < 5 个；超过要审视

3. **online DDL 加索引**：MySQL 5.6+ 支持在线加索引不锁表（除非用 LOCK=EXCLUSIVE）
4. **避免 `WHERE col != ?`、`OR`、`LIKE '%abc'`**——这些都不走索引

### 七、深挖追问 Q&A

**Q1：为什么 InnoDB 推荐用自增主键？UUID 不行吗？**

A：技术上都行，性能差别巨大。InnoDB 是**聚簇索引**，数据按主键 B+ 树物理排序。auto_increment 主键单调递增 → 新行**总追加到最右叶子页**，几乎没页分裂。UUID 随机分布 → 每次插入可能要从中间某页插，**触发页分裂**（一个 16KB page 满了要分裂成两个，重新分布 entry，是 IO 重活）。线上压测：UUID 主键的 INSERT QPS 大约比 auto_increment 慢 3-5 倍。

如果业务一定要 UUID（如对外接口防猜测），**别让 UUID 当主键**，单独加一列建唯一索引：
```sql
id BIGINT AUTO_INCREMENT PRIMARY KEY,
uuid CHAR(36) UNIQUE
```
对外暴露 uuid，内部主键还是 id。

**Q2：覆盖索引在我们项目里能省多少？怎么实测？**

A：当前查询 `SELECT time, rate FROM historicaldata WHERE ct1=? AND ct2=? ORDER BY time DESC LIMIT 1`——
- **无覆盖**：非聚簇索引 1 次（拿 id）+ 聚簇索引 1 次（回表拿 rate）= 2 次 IO
- **覆盖索引** `(ct1, ct2, time, rate)`：非聚簇索引 1 次直接拿 rate = 1 次 IO

理论上省 50% IO。但实测因为索引页通常在 buffer pool 内存里（17K 行表整个能装内存），实际时间差只有 ~0.2ms / 查询。**如果是 10M+ 行的大表，覆盖索引能让单查从 5ms → 1ms**。

实测方法：`SET profiling=1; SELECT ...; SHOW PROFILE FOR QUERY 1;` 看 `Sending data` 这一阶段时间。

**Q3：我有个查询是 `WHERE a=? AND b>? AND c=?`，索引 (a, b, c) 能完整用上吗？**

A：**只能用 a 和 b**。因为 `b>?` 是范围查询，B+ 树里 b 命中的子树**不再保证 c 有序**——所以 c 用不上索引（要走存储引擎层过滤，叫 ICP = Index Condition Pushdown，比无索引强但比走索引弱）。

**优化**：把范围列放最后建索引 `(a, c, b)`。这样 a, c 都是等值，最后 b 做范围——3 列全用上索引。**调换索引列顺序是优化范围查询的常用招**。

**Q4：B+ 树的叶子节点是单向链表还是双向？**

A：**双向链表**。这是 InnoDB 的设计。**原因**：① 支持 `ORDER BY ... DESC`（反向遍历，叫 Backward index scan）② 范围删除时要左右合并节点 ③ 树修复（如某叶子节点损坏）需要双向引用。代价：每个叶子节点多存一个 prev 指针 8 字节。

**Q5：哈希索引完全没用吗？什么时候用？**

A：有限场景有用——
- **Memory 引擎默认哈希索引**：临时表/数据缓存场景
- **InnoDB 的自适应哈希索引（AHI）**：InnoDB 自己监控某个 B+ 树非叶子节点的访问频率，如果热到一定程度自动建哈希缓存——**应用层透明**
- **Redis 是哈希存储**——单纯 K/V 缓存就是哈希思想

但**生产关系型数据库主索引绝不用哈希**——丢失范围查询能力。

**Q6：你查 EXPLAIN 看到 `type=ALL`，怎么排查？**

A：`type=ALL` = 全表扫，必须救。步骤：
1. **看 `key` 列**——如果 NULL，说明完全没用索引：检查 WHERE 列是否有索引 / 列顺序是否最左前缀
2. **看 `rows` 列**——估计扫描行数 vs 表总行数，如果接近表大小确认全扫
3. **检查 WHERE 表达式**：是否在索引列上用了函数（`WHERE DATE(time)='2025-01-01'` 让索引失效）/ 类型转换（varchar 列查 `WHERE col=123` 会隐式转，失效）
4. **检查 OR**：`WHERE a=? OR b=?` 通常导致全扫，改成 UNION
5. **如果 ORDER BY 慢**：看 `Extra` 是否有 `Using filesort`——文件排序，加 ORDER BY 列到索引能消除

**Q7：你们项目当前没用 ORM，未来切 SQLAlchemy 有什么坑？**

A：（详见 1.4 节）主要 3 坑：① **N+1 查询陷阱**——ORM 关联对象懒加载容易在循环里触发 N+1 ② **生成的 SQL 不可控**——ORM 有时生成性能差的 SQL，要 `.options(joinedload(...))` 显式控制 ③ **索引使用不直观**——查询是用 Python 表达式写的，看不出会用哪个索引，必须配 `echo=True` 看实际 SQL + EXPLAIN。

---

## 1.2 事务隔离级别 + MVCC + 锁——并发安全的基础

**面经原题**：
- "MySQL 4 个隔离级别 + 各能解决什么问题？"（蚂蚁后端高频）
- "幻读和不可重复读的区别？"
- "MVCC 怎么实现的？"
- "你们怎么避免超卖？"（电商 / 金融场景必问）

### 一、项目场景：我们的事务现状

CompassFXPulse 后端**所有 SQL 都是只读 SELECT**——5 个工具都不写 DB（写操作只在离线 script 里：`refresh.py` / `predict_rates.py`）。所以我们运行时**完全不触发事务并发问题**。

但**面试官一定会问支付场景**（特别是蚂蚁面试）——所以下面用"用户向银行账户转账"这种场景讲透。

### 二、事务的 ACID + 4 个隔离级别

**ACID** 是事务的 4 个不可缺特性：

| 字母 | 名称 | 含义 |
|---|---|---|
| **A** | Atomicity 原子性 | 事务里所有操作要么全成功要么全失败，不能中途出现"扣了 A 没加到 B" |
| **C** | Consistency 一致性 | 事务前后数据库都满足业务约束（如总金额守恒） |
| **I** | Isolation 隔离性 | 多个并发事务之间互相不"看见"对方中间状态 |
| **D** | Durability 持久性 | 事务一旦 commit，即使断电也不丢（靠 WAL/redo log） |

**4 个隔离级别**（SQL 标准从弱到强）：

#### 1. RU（Read Uncommitted，读未提交）
- 行为：事务 A 能读到事务 B **没 commit 的修改**
- 暴露问题：**脏读（dirty read）**——A 看到 B 写入的 X，但 B 后来 rollback，X **从未真存在**

#### 2. RC（Read Committed，读已提交）— Oracle / PostgreSQL 默认
- 行为：A 只读 B **已 commit 的数据**
- 解决：脏读
- 仍暴露：**不可重复读**——A 在事务里两次读同一行，中间 B 改并 commit 了，A 两次结果不同
- 经典 bug：转账时 A 先查余额 100，B 同时取走 50 commit，A 再查变 50——A 业务逻辑就错了

#### 3. RR（Repeatable Read，可重复读）— MySQL InnoDB 默认
- 行为：A 在整个事务期间，**多次读同一行结果一致**
- 解决：脏读 + 不可重复读
- SQL 标准下仍暴露：**幻读**——A 两次执行**范围查询**，中间 B INSERT 新行，A 两次结果不一样
- **MySQL InnoDB 通过 next-key lock 在 RR 级别基本解决了幻读**

#### 4. Serializable（串行化）
- 行为：所有事务**串行执行**
- 解决：所有问题；代价：性能极差

**记忆口诀**：
- 脏读 = 看到没提交的（RU 有，RC 起没）
- 不可重复读 = 同行两次读不一样（RC 有，RR 起没，**针对 UPDATE**）
- 幻读 = 范围查两次行数不一样（RR 标准有，**针对 INSERT/DELETE**）

### 三、MVCC（多版本并发控制）

**MVCC 是什么**：每行数据存**多个版本**，事务读的是"自己事务开始时刻的那个版本"，**不影响其他事务写**——读写不互斥。**这是 InnoDB 高并发能力的根本**。

**实现原理**（InnoDB）：

每行数据隐藏 3 个字段：
- `DB_TRX_ID` 最后修改该行的事务 ID
- `DB_ROLL_PTR` 指向 undo log 里的旧版本数据
- `DB_ROW_ID` 没主键时的隐式主键

事务读取时通过 **read view** 判断："这个版本对我可见吗？"

**RC vs RR 在 MVCC 上的差别**：
- **RC**：每次 SELECT 都**重新生成 read view** → 不可重复读
- **RR**：事务里**第一次 SELECT 时生成 read view 并冻结**

**关键认知**：MVCC 只对 SELECT 生效（"快照读"）。`SELECT FOR UPDATE` / `INSERT/UPDATE/DELETE` 叫**当前读**——读最新且加锁。

### 四、锁的家族

#### 按粒度
| 锁 | 锁的对象 |
|---|---|
| 表锁 | 整张表（MyISAM 默认） |
| 行锁 | 某一行（InnoDB 默认） |

#### 按模式
| 锁 | 含义 |
|---|---|
| **共享锁（S 锁）** | 读锁，`SELECT ... LOCK IN SHARE MODE` |
| **排他锁（X 锁）** | 写锁，`SELECT ... FOR UPDATE` |

#### InnoDB 特殊锁
- **Record Lock**：一行索引记录
- **Gap Lock**：索引记录间的间隙——防 INSERT，解决幻读
- **Next-Key Lock** = Record + Gap，InnoDB RR 级别默认

### 五、避免超卖的工程方案

**问题**：库存 100，10 个用户同时下单。

**方案 1：悲观锁**
```python
with db.transaction():
    stock = db.query("SELECT stock FROM goods WHERE id=1 FOR UPDATE")
    if stock > 0:
        db.execute("UPDATE goods SET stock=stock-1 WHERE id=1")
```

**方案 2：乐观锁（CAS）**
```python
affected = db.execute(
    "UPDATE goods SET stock=stock-1, version=version+1 "
    "WHERE id=1 AND version=:v",
    v=row.version)
if affected == 0:
    raise ConcurrentModification()
```

**方案 3：原子 SQL（推荐生产用）**
```python
affected = db.execute(
    "UPDATE goods SET stock=stock-1 WHERE id=1 AND stock>0"
)
if affected == 0:
    raise OutOfStock()
```

**方案 4：Redis 预扣 + 异步落库**（高并发场景）

### 六、深挖追问 Q&A

**Q1：MySQL 默认 RR，那互联网公司为什么很多用 RC？**

A：阿里规约推 RC。3 个原因：① RC 性能更好——RR 用大量 gap lock 并发写场景容易死锁；② 现代应用很少依赖严格不可重复读，业务自己用乐观锁兜底；③ RC 的 binlog 是 row 模式更稳定。我们项目用 RR 默认，但生产支付推荐 RC。

**Q2：长事务的危害？**

A：3 大危害：① 锁占用久——SELECT FOR UPDATE 跑 10 分钟其他都等；② undo log 堆积——长事务保留多版本数据让 read view 能读到旧版本；③ 主备同步延迟——长事务的 binlog 直到 commit 才同步。**生产规则**：事务不超过 1 秒；事务里禁止网络调用 / 文件操作 / RPC。

**Q3：怎么排查死锁？**

A：`SHOW ENGINE INNODB STATUS\G` 输出有 `LATEST DETECTED DEADLOCK` 段。InnoDB 探测到死锁会自动选回滚成本小的事务牺牲，应用层捕获 `Error 1213` 并 retry。生产开 `innodb_print_all_deadlocks=ON` 把死锁日志写到 error log。

---

## 1.3 慢查询定位的完整工作流

### 一、生产工作流（必背）

```
1. 开 slow query log
   └─ long_query_time=1（s），log 慢查询

2. 对 TOP query 跑 EXPLAIN
   └─ 看 type / key / rows / Extra

3. 判断是否走索引 + 是否最优
   └─ 没走：检查 WHERE 列 + 列顺序 + 函数转换
   └─ 走了但慢：检查索引选择性 / 是否 filesort

4. 优化方案
   ├─ 加索引 / 调列顺序
   ├─ 改 SQL（拆 OR 为 UNION，去 SELECT *）
   ├─ 业务层加缓存（我们 Phase 4.1 就是这层）
   └─ 终极方案：DB sharding / 分库分表
```

### 二、慢查询日志配置

```sql
SET GLOBAL slow_query_log=ON;
SET GLOBAL long_query_time=1;
SET GLOBAL log_queries_not_using_indexes=ON;
SET GLOBAL slow_query_log_file='/var/log/mysql-slow.log';
```

分析工具：
- `mysqldumpslow -s t -t 10 mysql-slow.log` — 按总时间排序前 10
- `pt-query-digest mysql-slow.log` — Percona Toolkit 高级分析

---

## 1.4 ORM vs raw SQL（Python 后端选型）

### 一、项目场景：我们为什么用 raw SQL

我们用 `mysql.connector`（raw SQL），不用 SQLAlchemy ORM。原因：
1. **5 个工具的 SQL 都很简单**（单表 SELECT）—— ORM 抽象收益小
2. **要看真实 SQL EXPLAIN**——ORM 生成的 SQL 不直观
3. **依赖更轻**——SQLAlchemy 启动加载慢

但生产项目（10+ 张表 + 关联查询）应该用 ORM。

### 二、ORM 的 N+1 陷阱

```python
users = session.query(User).limit(100).all()  # 1 次查询
for u in users:
    print(u.orders)  # 触发 100 次额外查询！
# 总共 101 次 query
```

**修法：eager load**
```python
users = session.query(User).options(joinedload(User.orders)).limit(100).all()
```

---

## 1.5 连接池设计与调参

### 一、项目场景：我们的连接池

`backend/app/db.py`：
```python
pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="compass_fx_pool",
    pool_size=20,        # Phase 4.1 从 5 → 20
    ...
)
```

### 二、连接池的本质

每次 `mysql_connect()` 要做：TCP 三次握手（1 RTT）+ SSL 握手（2 RTT）+ MySQL handshake + 鉴权（2 RTT），总共 ~5 RTT, ~50ms 在 localhost、~200ms 跨可用区。

连接池**预先建一组 conn**，请求来直接拿（< 1ms）。

### 三、pool_size 怎么定

**Java HikariCP 公式**：`connections = ((core_count × 2) + effective_spindle_count)`，8 核 + SSD → pool_size ≈ 17。

**反直觉**：池子大 ≠ 性能好。DB 同时处理太多并发因 lock contention / context switch 反而变慢。

**实战 rule of thumb**：
- 小服务：pool_size = (并发请求数 × 平均查询时间秒数) + buffer
- 生产：通常 10-50 每实例

### 四、深挖追问 Q&A

**Q：连接闲置太久会不会被 MySQL 主动断？**

A：会。MySQL `wait_timeout`（默认 8 小时）超时空闲连接会被服务端 close。**解法**：连接池要做健康检查——拿连接前 ping 一下；同时在客户端设 `auto_reconnect=True` 失败自动重连。

---

# 第 2 部分｜缓存设计（AI Agent 岗位必考）

## 2.1 Cache 三类问题（击穿 / 雪崩 / 穿透）完整解决

**面经原题**：
- "如果缓存挂了怎么办？"（蚂蚁高频）
- "缓存击穿怎么处理？"
- "Bloom Filter 是什么？怎么用？"

### 一、项目场景

`backend/app/cache.py` 实现了 TTLCache + Redis 双后端，Per-tool TTL（rate 1h / VaR 30min / RAG 10min）。但有 3 类问题没专门防：击穿 / 雪崩 / 穿透。

### 二、缓存击穿（Cache Breakdown）

**定义**：**单个热点 key 突然失效**，瞬间大量并发请求直接打 DB。

**典型场景**：双 11 爆款商品 key TTL 到期，10w QPS 涌进 DB；我们项目场景——`get_exchange_rate(USD, JPY)` TTL 1h 到点时如果有 100 并发都失效 → 100 个请求并发查 MySQL。

**4 种解法**：

**解法 A：互斥锁（mutex / single-flight）**

```python
def get_with_lock(key, fetch_db):
    val = cache.get(key)
    if val is not None:
        return val
    
    lock_key = f"lock:{key}"
    if redis.set(lock_key, 1, NX=True, EX=10):
        try:
            val = fetch_db(key)
            cache.set(key, val, ttl=3600)
            return val
        finally:
            redis.delete(lock_key)
    else:
        time.sleep(0.1)
        return cache.get(key) or fetch_db(key)
```

Go 的 `singleflight.Group` 是这个思想的语言级实现。

**解法 B：热点 key 永不过期 + 后台异步刷新**
- 缓存不设 TTL，后台 cron worker 每 N 分钟主动刷新

**解法 C：随机化 TTL + 提前刷新**
- TTL = 1h ± random(10min)
- 发现 TTL 剩余 < 10% 时异步触发刷新（不阻塞用户）

**解法 D：本地缓存兜底（多级缓存）**
- L1 in-memory（10 秒）+ L2 Redis（1h）
- L2 失效时 L1 兜 10 秒，10 秒内 L2 重建好就没事

### 三、缓存雪崩（Cache Avalanche）

**定义**：**大量 key 同时失效**，所有流量打到 DB。

**典型场景**：Redis 重启 / 主从切换 → 所有缓存清空 → DB 瞬间淹。

**5 种解法**：

**A 随机化 TTL**：1h ± random(10min)

**B 多级缓存**：L1 + L2，L2 雪崩时 L1 兜 5min 给重建时间

**C 熔断降级**：DB QPS 超阈值 → 服务直接返默认值或限流响应

**D Redis 主从 + 哨兵 / 集群**：主挂从顶

**E 缓存预热**：服务启动时主动加载热 key。我们项目 `main.py:_warmup_rag()` 是模型预热不是 cache 预热，但思想一致。

**项目里**：我们的 cache.py 有 Redis fallback——Redis 连不上自动退化为 in-memory TTLCache。

### 四、缓存穿透（Cache Penetration）

**定义**：**查询不存在的数据**，缓存 miss → DB miss → 不缓存 → 同样请求反复打 DB。**恶意攻击**最常见。

**3 种解法**：

**解法 A：缓存空值（NULL caching）**

```python
def get_user(user_id):
    val = cache.get(f"user:{user_id}")
    if val is not None:
        return val if val != "__NULL__" else None
    
    user = db.query("SELECT * FROM users WHERE id=?", user_id)
    if user is None:
        cache.set(f"user:{user_id}", "__NULL__", ttl=300)
        return None
    cache.set(f"user:{user_id}", user, ttl=3600)
    return user
```

TTL 要短（5 分钟），否则真有人 id=-1 后又改成 1，缓存还是 NULL 会有正确性问题。

**解法 B：Bloom Filter**

Bloom Filter 是**概率型数据结构**——判断"元素是否存在"，**有假阳性无假阴性**：
- 说"不存在"——一定不存在
- 说"存在"——可能存在（要去查 DB 确认）

**工作原理**：
- 内部是一个 bit array（如 10 亿 bit = 125MB）
- 添加：k 个不同 hash 函数 → k 个位置置 1
- 查询：k 个位置全为 1 = 可能存在；任一为 0 = 一定不存在

```python
from pybloom_live import BloomFilter

bf = BloomFilter(capacity=10_000_000, error_rate=0.001)
for uid in db.query("SELECT id FROM users"):
    bf.add(uid)

def get_user(user_id):
    if user_id not in bf:
        return None
    ...
```

**好处**：125MB 内存挡住所有"不存在 id"的请求。
**代价**：① 假阳性少量请求穿透到 DB ② 删除困难（要用 Counting Bloom Filter）

**解法 C：参数校验**：拒绝 id < 0 等非法值

### 五、解决方案选择矩阵

| 场景 | 推荐解法 |
|---|---|
| 单个热 key 偶尔失效 | 解法 A 互斥锁 |
| 大量 key 同时失效（雪崩） | TTL 随机化 + 多级缓存 + Redis 哨兵 |
| 恶意脚本攻击不存在的 id | Bloom Filter + 参数校验 |
| 业务自然的 NULL | 缓存空值（短 TTL） |

### 六、深挖追问 Q&A

**Q1：缓存击穿 vs 雪崩区别？**

A：**击穿 = 单点失效**（一个热 key + 高并发）；**雪崩 = 群体失效**（很多 key 同时）。**击穿的解法是 single-flight**（让 1 个请求查 DB，其他等）；**雪崩的解法是分散失效时间 + 限流降级**。混淆这俩问题答案完全不一样。

**Q2：Bloom Filter 怎么调参数？**

A：3 个变量——n=元素数, m=bit 数组大小, k=hash 函数个数, p=假阳性率。关系：`p = (1 - e^(-kn/m))^k`，最优 `k = (m/n) × ln(2)`。**典型配置**：1000 万元素 + 0.1% 假阳性 = ~125 MB + 10 个 hash。

**Q3：Bloom Filter 怎么删除元素？**

A：标准 Bloom Filter **不支持删除**。**2 个方案**：
- **Counting Bloom Filter**：每个位置不是 0/1 而是计数器
- **重建**：周期性根据 DB 全量重建

**Q4：Redis 挂了怎么保证服务可用？**

A：3 层防御——① 应用层 fallback（我们 cache.py 自动退化为 in-memory）② Redis 主从 + 哨兵自动 failover ③ 限流 + 降级。

---

## 2.2 Cache 4 种读写模式

### 一、4 种模式总览

| 模式 | 谁写 cache | 谁读 cache |
|---|---|---|
| **Cache-Aside（旁路缓存）** | **应用** | **应用** |
| Read-Through | cache 层 | cache 层 |
| Write-Through | cache 层 | cache 层 |
| Write-Back（Write-Behind） | cache 层（异步） | cache 层 |

业内 95% 用 Cache-Aside，我们项目也是。

### 二、Cache-Aside 详解

**写流程**（关键，有坑）：
```
正确：先 update DB → 再 del cache
错误：先 del cache → 再 update DB
错误：先 update DB → 再 update cache（直接覆写而不是删）
```

**为什么 "先 update DB → 再 del cache" 正确**：

如果是 "先 del cache → 再 update DB"，考虑：
- T1：写线程 del cache
- T2：读线程查 cache miss → 查 DB 拿到旧值 X → 写 cache
- T3：写线程 update DB
- **结果：cache=旧值，DB=新值，永久不一致**

如果是 "先 update DB → 再 del cache"：
- T1：写线程 update DB
- T2：读线程查 cache miss → 查 DB 拿到新值 → 写 cache
- T3：写线程 del cache（cache 没了下次重建会从 DB 拿，OK）

**为什么 del 而不是 update**：并发写时两个写对 cache 的 update 顺序可能和 DB 顺序相反 → 不一致。**del 后让 cache miss 重建是简单可靠的**。

---

## 2.3 Redis 5 基本数据结构与底层

### 一、5 基本数据结构 + 底层

| 类型 | 底层（小数据） | 底层（大数据） | 典型用途 |
|---|---|---|---|
| **String** | int / SDS | SDS | KV 缓存、计数器（INCR）、分布式锁（SET NX） |
| **List** | quicklist | quicklist | 消息队列、最近访问列表 |
| **Hash** | ziplist | hashtable | 用户对象 |
| **Set** | intset / hashtable | hashtable | 标签、共同好友、UV |
| **ZSet** | ziplist | **skiplist + hashtable** | 排行榜、延迟队列 |

### 二、SDS（简单动态字符串）

```c
struct sdshdr {
    int len;      // 已用长度
    int free;     // 剩余空间
    char buf[];
};
```

**比 C 字符串好在哪**：
1. O(1) 获取长度（C 字符串要 strlen 遍历）
2. 二进制安全（C 字符串遇 \0 截断）
3. 预分配空间（避免每次扩容 realloc）
4. 惰性释放

### 三、为什么 ZSet 用 skiplist 不用红黑树

1. **范围查询天然友好**——ZRANGEBYSCORE 是 ZSet 最常用操作
2. **实现简单**——Redis 作者 antirez 在 Antirez weblog 写过原因："skiplist is simpler to implement, debug, and modify"
3. **缓存友好**——节点物理连续，CPU cache hit 率高

---

## 2.4 Redis 持久化（RDB / AOF / 混合）

### 一、RDB

**定时全量快照**存磁盘。

**优点**：文件小、恢复快。
**缺点**：会丢最近 N 分钟数据；fork() 在大内存下慢。

**实现**：`fork()` 子进程做 dump（COW 写时复制机制）。

### 二、AOF

**每次写命令追加到日志文件**，重启时重放。

**3 种 fsync 策略**：
- `always`：每次写都 fsync（最安全 + 最慢）
- `everysec`（默认）：每秒 fsync（折中，最多丢 1s）
- `no`：完全交给 OS

**AOF rewrite**：AOF 过大时 fork() 子进程扫描内存 dump 等价最小命令集合（对同一个 key set 100 次只保留最后一次）。

### 三、混合持久化（Redis 4.0+ 默认）

`aof-use-rdb-preamble yes`——AOF rewrite 时先写 RDB 格式到头部，再追加新命令。恢复时先 load RDB（快）+ 重放尾部命令（少量）。

**生产推荐**：
```
save 900 1
appendonly yes
appendfsync everysec
aof-use-rdb-preamble yes
```

### 四、深挖追问 Q&A

**Q：fork() 在大内存 Redis 上为什么慢？**

A：fork() 不是真复制内存（COW），但**需要复制页表**——64GB 内存 Redis 页表 ~128MB（64GB / 4KB × 8 字节 page entry）。fork() 时内核必须把这 128MB 整个复制——几百 ms 到秒级，**主进程阻塞**。生产 Redis 实例建议 < 32GB。

---

## 2.5 Redis 高可用（主从 / 哨兵 / 集群）

### 一、主从复制

```
Master ──异步同步命令──> Slave 1
              \────> Slave 2
              \────> Slave 3
```

**首次同步（full sync）**：
1. Slave 发 `PSYNC`
2. Master 触发 `BGSAVE` 生成 RDB
3. Master 发 RDB + 期间新命令缓冲到 `repl_backlog_buffer`
4. RDB 同步完后发 backlog
5. 后续命令实时同步

**断线重连优化（partial sync）**：Slave 重连时 master 的 backlog 还有它断线时的 offset → **只发增量**。

### 二、哨兵（Sentinel）

3 个哨兵节点监控 master，挂了**投票选举**新 master。

**failover 流程**：
1. 30s 收不到 master ping → SDOWN
2. 多数 Sentinel 同意 → ODOWN
3. Sentinel 投票选 leader
4. Leader 从 slaves 选新 master（优先级 + 复制 offset 大）
5. 通知 slaves 改 replicate 目标
6. 通知客户端新 master 地址

### 三、Redis Cluster

**水平分片**——16384 个 slot，每个 key 通过 `CRC16(key) % 16384` 映射到 slot。

**Hash Tag**：`{user:1000}.profile` 和 `{user:1000}.orders` 因为 `{}` 内一样 → 同 slot，**保证多 key 操作可用**。

### 四、深挖追问 Q&A

**Q：哨兵能解决脑裂吗？**

A：**有限**。网络分区可能出现两个 master 同时接收写。**Redis 配置 `min-replicas-to-write 1`**——master 要求至少 1 个 slave 接收复制才接受写，能减轻脑裂数据丢失。

---

## 2.6 多级缓存设计

### 一、生产标配的多级缓存

```
请求 → [CDN] → [Nginx 静态缓存] 
            → [应用进程内缓存 L1（如 Caffeine / TTLCache）]
            → [Redis 集群 L2]
            → [DB]
```

每级特点：
- L1（进程内）：纳秒级，但不共享
- L2（Redis）：毫秒级，全局共享
- DB：10ms+，权威数据

**我们项目当前**：L1 或 L2 二选一。生产升级 Phase 4.6 路线：L1 + L2 双层。

### 二、热点 key 发现

**业务问题**：双 11 期间某商品 QPS 飙到 10w——单 Redis 节点撑不住（~10w QPS 上限）。

**解决方案 1：本地缓存兜底**——发现热 key 后在 L1 也缓存。

**解决方案 2：热点 key 分散**——`product:1001` 分散为 `product:1001:0` ~ `product:1001:9` 10 个副本。

**发现方法**：
- `redis-cli --hotkeys`（4.0+）
- 业务监控：每个 key 访问次数累计

---

# 第 3 部分｜并发与异步（AI Agent 岗位必考）

## 3.1 线程池 7 参数 + 调参方法论

### 一、ThreadPoolExecutor 7 参数

```java
new ThreadPoolExecutor(
    int corePoolSize,                       // 核心线程数（常驻）
    int maximumPoolSize,                    // 最大线程数（含临时）
    long keepAliveTime,                     // 临时线程空闲多久销毁
    TimeUnit unit,
    BlockingQueue<Runnable> workQueue,      // 任务队列
    ThreadFactory threadFactory,
    RejectedExecutionHandler handler        // 拒绝策略
);
```

### 二、任务到来时的处理流程（必背 4 步）

```
新任务 .execute(task)
   ↓
当前线程数 < corePoolSize?
   ├─ 是 → 新建核心线程
   ↓ 否
入队 workQueue 成功?
   ├─ 是 → 等空闲线程拉
   ↓ 否（队列满）
线程数 < maximumPoolSize?
   ├─ 是 → 新建临时线程
   ↓ 否
触发 RejectedExecutionHandler
```

**注意**：第 2 步是**先入队再扩线程**——跟直觉相反，是 Java 的设计：优先用最少线程做事。

### 三、4 种拒绝策略

- `AbortPolicy`（默认）：抛异常
- `CallerRunsPolicy`：**调用线程自己跑**——反压效果好
- `DiscardPolicy`：丢弃新任务，不抛异常（危险）
- `DiscardOldestPolicy`：丢弃队列最老的

### 四、调参方法论

**CPU 密集型**：`corePoolSize ≈ CPU 核数`，公式 `N = N_cpu + 1`

**I/O 密集型**：`corePoolSize = CPU 核数 × 2` 到更多
- **Little's Law**：`N = QPS × avg_latency_seconds`
- 例：100 QPS × 100ms = 10 线程

**LLM 应用**：大头等 LLM API（强 I/O），一般 N = 20-50 起步。我们 FastAPI `asyncio.to_thread()` 默认 thread pool = 40。

### 五、为什么阿里规约不让用 `Executors`

`Executors.newFixedThreadPool(N)`：内部用 `LinkedBlockingQueue`（**无界**）→ 任务积压 OOM。

`Executors.newCachedThreadPool()`：maxPoolSize = `Integer.MAX_VALUE`→ 线程无限增长 OOM。

**正确写法**：
```java
new ThreadPoolExecutor(
    10, 50, 60, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(1000),
    new ThreadFactoryBuilder().setNameFormat("biz-%d").build(),
    new ThreadPoolExecutor.CallerRunsPolicy()
);
```

### 六、深挖追问 Q&A

**Q：corePoolSize=10 且队列已经 100 个任务，第 11 个任务怎么处理？**

A：**还是入队**。10 个核心线程满了不会再新建。只有队列也满了才触发新建临时线程到 max。

---

## 3.2 Python GIL + asyncio 事件循环深解

### 一、GIL（Global Interpreter Lock）

**GIL 是什么**：CPython 解释器的**全局锁**——**同一进程内同时只有 1 个线程能跑 Python 字节码**。

**为什么有 GIL**：CPython 的内存管理（引用计数）不是 thread-safe；没有 GIL 要给每个对象加锁，开销大；历史包袱。

**结果**：
- **CPU 密集型 Python 多线程没有真并行**
- **I/O 密集型 Python 多线程 OK**（等 I/O 时释放 GIL）

**绕开 GIL 的 3 个方法**：
1. **多进程**（`multiprocessing` / `ProcessPoolExecutor`）
2. **C 扩展**（NumPy / PyTorch 在 native code 里释放 GIL）
3. **asyncio**——单线程不存在 GIL 争用

### 二、asyncio 事件循环深解

```python
import asyncio

async def fetch(url):
    print(f"start {url}")
    await asyncio.sleep(1)  # ← await 时让出控制权
    print(f"done {url}")

async def main():
    # 3 个任务并发，总耗时 1s 不是 3s
    await asyncio.gather(fetch("a"), fetch("b"), fetch("c"))

asyncio.run(main())
```

**事件循环本质**：一个 while 循环
```python
while True:
    # 1. 处理到期的定时器
    # 2. 处理就绪的 I/O
    # 3. 调度可继续跑的协程
    # 4. 阻塞等待下一个 I/O 事件（select / epoll / kqueue）
```

**关键**：协程在 `await` 时让出控制权——**asyncio 是协作式调度，不是抢占式**。

**坑：阻塞调用会卡死事件循环**
```python
async def bad():
    time.sleep(1)  # 阻塞！整个事件循环卡 1s
    
async def good():
    await asyncio.sleep(1)  # 让出
```

**asyncio 桥接同步代码**：
```python
result = await asyncio.to_thread(sync_function, args)
```

我们项目 `routes_async.py:agent_endpoint()` 就用这招——把 `stream_agent`（同步 generator）放到 thread pool。

### 三、I/O Bound vs CPU Bound

| 类型 | 最优方案 |
|---|---|
| **I/O Bound** | asyncio / 多线程 |
| **CPU Bound** | 多进程 / C 扩展 / Rust 改写 |

**LLM 应用 = 重度 I/O Bound**——等 DeepSeek API、等 MySQL、等 GPU 计算（Python 不直接算）。**所以 asyncio 完美**。

### 四、深挖追问 Q&A

**Q：你说 Python 多线程能做 I/O 密集，那 asyncio 比多线程优势在哪？**

A：3 点——
- **内存开销**：每线程 ~8MB stack，asyncio 协程 ~几 KB。1 万并发：线程 80GB 装不下，协程 < 1GB
- **切换开销**：线程切换 ~微秒级 + GIL 争用；协程切换 ~纳秒级
- **代码风格**：async/await 流程线性可读；多线程要处理同步原语

**Q：什么时候不该用 asyncio？**

A：① CPU 密集任务——要多进程；② 依赖库不支持 async；③ 简单脚本——asyncio 学习曲线，sync 更直观。

---

## 3.3 协程 vs 线程 vs 进程

| 维度 | 进程 | 线程 | 协程 |
|---|---|---|---|
| 内存空间 | 独立 | 共享 | 共享 |
| 切换开销 | ~1ms | ~微秒 | ~纳秒 |
| 启动开销 | ~10ms | ~1ms | ~微秒 |
| 调度方 | OS | OS | 应用（事件循环）|
| Python 真并行 | ✅ | ❌（GIL）| ❌（单线程）|

**类比**：进程 = 公司；线程 = 公司里的员工；协程 = 员工脑子里的多个任务想法。

---

## 3.4 同步原语家族

### 5 种核心

**1. 互斥锁（Mutex / Lock）**：单一持有者
```python
lock = threading.Lock()
with lock:
    counter += 1
```

**2. 读写锁（RWLock）**：多读者共存，写互斥；读多写少场景比互斥锁性能好

**3. 信号量（Semaphore）**：允许 N 个持有者
```python
sem = threading.Semaphore(10)  # 最多 10 个并发
with sem:
    call_api()
```

**4. 条件变量（Condition）**：等待某条件成立——`wait()` 释放锁阻塞、`notify()` 唤醒

**5. CAS（Compare-And-Swap）**：原子操作——硬件指令（x86 `cmpxchg`）实现，无锁编程基础

**项目里**：`app/rate_limit.py:TokenBucket` 用 `threading.Lock` 保护 token 数。

---

## 3.5 分布式锁完整对比

### 一、3 个要求

1. **互斥**：同一时刻只有一个 client 持有
2. **不死锁**：持有者崩了锁能释放
3. **容错**：部分节点挂仍可用

### 二、方案 1：Redis SETNX（单节点）

```python
ok = redis.set(lock_key, request_id, NX=True, EX=10)
if not ok:
    raise LockBusy()

# 释放（必须 Lua 保证原子）
release_lua = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
redis.eval(release_lua, 1, lock_key, request_id)
```

**3 个必须**：① `NX=True`——不存在才设；② `EX=10`——TTL 防死锁；③ 释放用 Lua 检查 owner——防误删别人的锁

**3 个坑**：① TTL 短业务没跑完锁过期；② TTL 长服务崩后等很久；③ 主从异步——master 设了 lock crash 还没同步给 slave

### 三、方案 2：Redlock（多 Redis 节点）

5 个独立 Redis 节点，**依次** SETNX，3 个成功才算获得锁。

**有争议**：Martin Kleppmann 反驳——时钟漂移 / 网络分区下不安全。antirez 回应：业务场景不要求强一致 Redlock 够用。

业内现状：金融生产强一致选 **Zookeeper / etcd**。

### 四、方案 3：Zookeeper（强一致 CP）

ZK 是 Zab 协议（类 Paxos）的协调服务。

**加锁**：
1. 在 `/locks/x/` 下创建临时顺序节点 `lock-0001`
2. 列出所有子节点，看自己是否最小
3. 是 → 持有锁；否 → watch 比自己小的那个节点

**优势**：临时节点——client 断连 znode 自动消失，**无需 TTL**

**劣势**：比 Redis 慢（ms 级 vs μs 级）；部署成本高（3-5 节点集群）

### 五、对比表

| 方案 | 一致性 | 性能 | 适合 |
|---|---|---|---|
| Redis SETNX | 弱 | < 1ms | 非金钱场景 |
| Redlock | 中（争议） | 中 | 折中 |
| Zookeeper | 强 CP | ms 级 | 金融支付 |
| etcd | 强 CP | ms 级 | 云原生 |

---

## 3.6 幂等性设计模式

### 一、定义

**幂等性**：同一个操作执行 N 次和执行 1 次效果**完全一样**。

**为什么必须做**：网络超时重试场景——client 重试可能导致 server 处理 N 次。

**典型场景**：支付（扣 N 次钱）、发短信、创建订单、LLM 调用。

### 二、5 种实现模式

**模式 1：唯一约束**
```sql
INSERT INTO orders (request_id, ...) VALUES (?, ...)
-- request_id 唯一索引，第二次插入冲突返回原结果
```

**模式 2：状态机**
```python
def pay(order_id):
    order = db.get(order_id)
    if order.status == 'paid':
        return Success("already paid")
    ...
```

**模式 3：Token 模式**
```python
token = server.gen_token(user_id)
def transfer(token, ...):
    if not redis.delete(token):  # 原子删除
        raise InvalidOrUsedToken()
    ...
```

**模式 4：去重表 + request_id**
```python
def process(request_id, payload):
    if not redis.set(f"req:{request_id}", "1", NX=True, EX=86400):
        return get_cached_result(request_id)
    result = do_business(payload)
    cache_result(request_id, result)
    return result
```

**模式 5：版本号（CAS）**
```sql
UPDATE accounts SET balance = balance - 100, version = version + 1
WHERE id = 1 AND version = 5
```

### 三、LLM 调用场景

我们项目调 DeepSeek 超时重试——**Phase 4.1 缓存层 隐式实现了请求级幂等**——同 query 重发不会重复算 LLM。

---

## 3.7 限流算法

### 一、4 种主流算法

**1. 固定窗口（Fixed Window）**：每 1s 累计计数，到边界归零。**边界 burst 问题**——0.999s 到 1.001s 期间可能 2× limit 通过。

**2. 滑动窗口（Sliding Window）**：用 Redis ZSet 存请求时间戳，查询时 `ZRANGEBYSCORE` 拿最近 1s 内请求数。

**3. Token Bucket（令牌桶）— 我们项目用这个**
- 桶容量 burst
- 以 rate 匀速补 token
- 请求消耗 1 token，桶空就拒
- **允许 burst**

```python
class TokenBucket:
    def __init__(self, rate, burst):
        self.rate, self.burst = rate, burst
        self.tokens = burst
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()
    
    def allow(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.burst, 
                              self.tokens + (now - self.last_refill) * self.rate)
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False
```

**4. Leaky Bucket（漏桶）**：桶内队列匀速出队处理；不允许 burst

### 二、Token vs Leaky Bucket

| 维度 | Token Bucket | Leaky Bucket |
|---|---|---|
| 输入 | 可 burst | 任意速率 |
| 输出 | 可 burst | 匀速 |
| 适合 | API 限流（允许小爆发）| 流量整形（强匀速） |

**项目**：`app/rate_limit.py` Token Bucket——10 rps + 20 burst。

### 三、分布式限流

单机限流的扩展：Redis + Lua 实现分布式 Token Bucket（保证原子）。

### 四、深挖追问 Q&A

**Q：限流应该放在哪一层？**

A：**多层限流**最稳——网关层（Nginx limit_req）IP 级 + 应用层（业务限流）用户/接口级 + 服务间（限制 LLM API 并发）保护下游。单层限流容易被绕过。

---

# 第 4 部分｜网络与协议

## 4.1 TCP 三 / 四次握手 + TIME_WAIT 优化

### 一、三次握手

```
Client                    Server
  | -- SYN, seq=x --->     |   ① "我要连，初始序号 x"
  | <-- SYN+ACK, seq=y --  |   ② "收到，我也要连，序号 y"
  |     ack=x+1            |
  | -- ACK, ack=y+1 -->    |   ③ "收到你的 y"
```

**为什么不是 2 次**：省掉 ③，Server 不知道 Client 真收到了 ②。会出现历史延迟连接复活——很久之前的 SYN 包延迟到达，Server 回 SYN+ACK 但 Client 已下线，Server 半开连接浪费资源。

### 二、四次挥手

```
Client                          Server
  | -- FIN -->                    |   ① "我没数据要发了"
  | <-- ACK --                    |   ② "收到"
  |                               |
  |     ... Server 可能还在发 ... |
  |                               |
  | <-- FIN --                    |   ③ "我也没了"
  | -- ACK -->                    |   ④ "收到"
  |    TIME_WAIT 2*MSL            |
```

**为什么是 4 次**：TCP 全双工，每方向独立关闭。

### 三、TIME_WAIT

主动关闭方在最后 ACK 后**进入 TIME_WAIT 状态 2*MSL**（默认 4 分钟）。

**两个原因**：
1. 防止最后 ACK 丢失——server 没收到会重发 FIN
2. 让网络中的延迟包消亡

**生产化坑**：高并发短连接积累大量 TIME_WAIT——每个占 1 个本地端口（65535 上限）。

**优化**：
- `net.ipv4.tcp_tw_reuse=1`
- HTTP keep-alive 替代短连接
- 应用层连接池

---

## 4.2 HTTP/1.1 → HTTP/2 → HTTP/3

### 一、HTTP/1.1 痛点

- **队头阻塞**：一个 TCP 连接上请求必须串行
- 每个请求一个 TCP 连接——握手开销
- HTTP 头部纯文本——浪费带宽

### 二、HTTP/2（2015）

- **二进制帧**
- **多路复用**——单个 TCP 上多个 stream 并发，消除应用层队头阻塞
- **HPACK 头部压缩**
- **server push**

仍有：TCP 层队头阻塞。

### 三、HTTP/3 / QUIC（2022）

**改用 UDP**——QUIC 是基于 UDP 的可靠传输协议。

好处：
- **消除 TCP 队头阻塞**——每 stream 独立丢包恢复
- 0-RTT 建连
- 连接迁移（WiFi 切 5G IP 变了不断）
- 加密内建

### 四、深挖追问 Q&A

**Q：为什么 HTTP/3 不直接改 TCP？**

A：TCP 是 OS 内核实现的，改 TCP 要所有操作系统升级，N 年才能普及。QUIC 在**用户态**实现可靠传输，应用直接升级就能用——**绕开 OS 升级周期**。

---

## 4.3 HTTPS 完整握手 + TLS 1.3

### 一、TLS 1.2 完整握手（4 RTT 共）

1. TCP 三次握手（1 RTT）
2. TLS 握手（2 RTT）：Client Hello → Server Hello + 证书 → Client Key Exchange → 双方推导对称密钥
3. HTTPS 业务请求（1 RTT）

### 二、TLS 1.3（2018）优化

- TLS 握手只需 1 RTT
- **0-RTT 重用**（PSK）——首次请求带数据无额外 RTT
- 但有 **replay 风险**，不适合非幂等请求

### 三、HTTPS 3 大功能

1. **加密**（AES 对称密钥）
2. **完整性**（MAC 校验）
3. **认证**（证书验证 server 身份）

### 四、对称 vs 非对称

握手用**非对称**（RSA / ECDHE）协商对称密钥；业务用**对称**（AES）传数据。**非对称慢 1000×**，只在握手用一次划算。

---

## 4.4 WebSocket / SSE / 长轮询对比（Streaming 必考）

### 一、4 种流式技术对比

| 技术 | 协议 | 方向 | 适合 | 我们项目 |
|---|---|---|---|---|
| **轮询** | HTTP | client → server 每秒查 | 简单 | 不用 |
| **长轮询** | HTTP | client 请求 hang 着等 | 不严重的实时 | 不用 |
| **SSE** | HTTP | server → client 单向流 | **LLM 输出 / 通知** | ✅ Agent 流式输出 |
| **WebSocket** | 独立协议 | 双向全双工 | 聊天 / 游戏 / 协作 | 不用 |

### 二、SSE 详解（我们用的）

**协议**：HTTP 长连接 + `Content-Type: text/event-stream` + 服务器持续 yield `data: {...}\n\n`。

**优点**：
- 基于 HTTP，**穿透 CDN / 代理 / 防火墙友好**
- 自动重连（浏览器 EventSource API 原生支持）
- 文本协议，调试简单

**项目实现**：`backend/app/agent/core.py:stream_agent()`
```python
def stream_agent(user_text):
    for chunk in _chunk_text(final_text, chunk_size=4):
        yield f"data: {json.dumps({'text': chunk})}\n\n"
    yield "data: {\"text\": \"[DONE]\"}\n\n"
```

前端 `EventSource`：
```javascript
const source = new EventSource('/api/agent?query=...');
source.onmessage = (e) => {
    const data = JSON.parse(e.data);
    appendToUI(data.text);
};
```

### 三、WebSocket vs SSE 怎么选

**选 WebSocket**：双向通信 / 二进制数据 / 极低延迟

**选 SSE**：单向 server → client（**LLM 流式输出标配**）/ 不想引入新协议 / 想用 HTTP/2 多路复用

### 四、深挖追问 Q&A

**Q：你们项目为什么选 SSE 不选 WebSocket？**

A：3 点——
- LLM 每次只发一次 prompt + 等流式回复，**单向就够**
- SSE 是 HTTP 长连接，nginx / CDN 完全透明；WebSocket 需特殊配置 `Upgrade` 头
- 浏览器 `EventSource` 原生支持自动重连
- 调试简单——`curl -N /api/agent` 直接能看流

WebSocket 在我们场景是**过度设计**。

**Q：SSE 限制 6 个并发是什么？怎么绕开？**

A：HTTP/1.1 浏览器对同一个 origin 默认**最多 6 个 TCP 连接**——第 7 个 SSE 会 hang。解法：① 用 HTTP/2 多路复用 ② 用不同 subdomain。

---

## 4.5 反向代理与负载均衡算法

### 一、反向代理

```
浏览器 → [Nginx] → ┬→ Backend 1
                   ├→ Backend 2
                   └→ Backend 3
```

用途：SSL 终止 / 静态资源缓存 / 负载均衡 / 限流 / API gateway

### 二、负载均衡算法

| 算法 | 行为 | 适合 |
|---|---|---|
| **Round Robin** | 轮流分发 | backend 性能均等 |
| **Weighted RR** | 按权重分发 | backend 性能不均 |
| **Least Connections** | 给当前连接数最少的 | 处理时间不均 |
| **IP Hash** | 同 IP 总到同 backend | 需要 session 粘性 |
| **Consistent Hash** | 一致性哈希 | 缓存场景 |

### 三、生产 Nginx 配置（含 SSE 优化）

```nginx
upstream llm_backend {
    least_conn;
    server backend1:8080 max_fails=3 fail_timeout=30s;
    server backend2:8080 weight=2;
}

server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    limit_req zone=api burst=20 nodelay;
    
    location / {
        proxy_pass http://llm_backend;
        proxy_buffering off;        # SSE 不能 buffer！
        proxy_read_timeout 600s;    # LLM 长连接要够长
    }
}
```

**SSE 关键**：`proxy_buffering off`——不然 nginx 会等响应完整才转发，破坏流式效果。

---

# 第 5 部分｜消息队列与异步管道

## 5.1 Kafka 高吞吐 4 大原因

### 一、3 大 MQ 对比

| | Kafka | RabbitMQ | RocketMQ |
|---|---|---|---|
| **吞吐** | **百万级 QPS** | 万级 | 十万级 |
| **延迟** | ms 级 | μs 级 | ms 级 |
| **持久化** | 磁盘顺序写 | 内存优先 | 磁盘 |
| **典型用途** | 日志 / 流处理 | 业务异步 / RPC | 金融订单 |

### 二、Kafka 高吞吐 4 大原因（必背）

**1. Partition 横向扩展**
- 一个 topic 切 N partition
- 每个 partition 独立顺序写、独立消费
- **N 个 partition = N 倍并行**

**2. 磁盘顺序写**
- HDD 顺序写 ~100 MB/s（接近内存）
- HDD 随机写 ~0.5 MB/s
- Kafka 把消息按 partition 顺序追加到 append-only log

**3. Zero-copy（sendfile syscall）**
- 传统：磁盘 → page cache → 用户态 buffer → socket buffer → 网卡（4 次 copy）
- Zero-copy：磁盘 → page cache → 网卡（**2 次 copy，0 次用户态参与**）

**4. 批量发送 + 压缩**
- Producer 攒一批消息一次发
- 压缩比 5-10×（gzip / snappy / lz4）

### 三、Kafka 核心概念

- **Topic**：消息主题
- **Partition**：topic 的物理分片
- **Offset**：消费者在 partition 里的进度指针
- **Consumer Group**：一组消费者协作，每 partition 只被 group 内 1 个 consumer 消费

---

## 5.2 消息可靠性的 3 段防护

**3 个环节都可能丢消息**：

**1. 生产端**：消息没发到 broker
- 解法：`ack=all`（所有副本写完才算成功）+ retry

**2. Broker 端**：消息收了但还没刷盘 broker 挂了
- 解法：`min.insync.replicas=2` + `unclean.leader.election.enable=false`

**3. 消费端**：消费了但还没处理就 commit offset 了
- 解法：**手动 commit**——处理完业务才 commit（**至少一次**）

**精确一次（exactly-once）**：Kafka 0.11+ 支持，配合 idempotent producer + transactional commit。代价大，业内多数用 at-least-once + 业务幂等。

---

## 5.3 AI Agent 场景的 MQ 应用

我们项目当前不用 MQ。生产化用例：

**1. LLM 任务异步化**
- 用户提交问题 → 写一条 Kafka 消息（task_id）→ 立即返 task_id
- 后端 worker 异步消费 → 调 LLM → 写结果到 Redis（key=task_id）
- 用户通过 task_id 查结果
- **解决**：长 LLM 任务用户不用 hang HTTP 连接

**2. 数据 pipeline 异步**
- `scripts/refresh.py` 跑完 publish "data_updated" 消息
- 索引服务订阅，触发 RAG 索引重建

**3. 用户行为日志**
- 每次 Agent 调用打一条 Kafka log
- 离线分析模型质量、热门 query、bad case 挖掘

---

# 第 6 部分｜架构设计与模式

## 6.1 5 种最常考的设计模式 + 项目对应

### 1. 单例（Singleton）

```python
class Settings:
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

**项目对应**：`app/cache.py:get_backend()` / `app/db.py:get_pool()` / `app/rate_limit.py:get_default()`

**单例反模式**：全局可变状态影响测试。**FastAPI 用 `Depends` 依赖注入是替代方案**。

### 2. 工厂方法

```python
def get_backend() -> CacheBackend:
    if os.environ.get("REDIS_URL"):
        return RedisCacheBackend(...)
    return TTLCacheBackend(...)
```

**项目对应**：cache backend 工厂、judge model 工厂

### 3. 策略

**项目对应**：Phase 4.2 `JudgeClient` 可换不同 LLM 当评委——同一接口 `score(query, run) → verdict`。

### 4. 责任链

**项目对应**：Phase 4.3 的 **5 层注入防御**：
```
Layer 1 (regex) → Layer 2 (system prompt) → Layer 3 (args)
              → Layer 4 (sanitizer) → Layer 5 (Reflector)
```

### 5. 装饰器

**项目对应**：`@mcp.tool()` / `@app.route()` / `@retry`——把函数包装成另一种能力。

---

## 6.2 熔断 / 降级 / 重试三件套

### 一、3 个机制

**1. 重试（Retry）**
- 网络抖动 / API rate limit 等 transient 错误 → 自动重试
- **必须指数退避**：1s, 2s, 4s, 8s
- **必须有上限**：3-5 次后认输

**2. 熔断（Circuit Breaker）**
- 监控失败率，**失败率 > 阈值时切断后续请求**直接返默认值
- 3 状态：closed（正常）→ open（熔断）→ half-open（试探）

**3. 降级（Fallback）**
- 调用失败 / 熔断时返**降级数据**
- 例：DeepSeek 挂了切到本地 Qwen3-LoRA
- 例：RAG 召回失败时让 LLM 用训练数据答 + 加免责

### 二、项目升级路线

我们目前没专门做熔断。Phase 5 计划：
```python
@circuit_breaker(failure_threshold=0.5, recovery_time=60)
@retry(max_attempts=3, backoff_factor=2)
def call_deepseek(messages):
    return client.chat.completions.create(messages=messages, ...)

def fallback_llm(messages):
    return call_local_qwen_lora(messages)
```

业内库：Java 的 Resilience4j / Python 的 `tenacity`（retry）

---

## 6.3 分布式事务

### 4 种方案

**1. 2PC（两阶段提交）**：协调器先 prepare 所有节点 → 全部 ready 后发 commit。**强一致**但**慢 + 协调器挂时死锁**。几乎不用。

**2. TCC（Try-Confirm-Cancel）**：Try 阶段预占资源 → Confirm 真扣 → 任一失败 Cancel 释放预占。实现复杂但**性能比 2PC 好**。

**3. Saga 补偿事务**：每步独立 commit，失败时**倒序执行补偿**。实现简单但中间态可见。

**4. 事务消息**（RocketMQ 原生支持）：业务先发 half-message → 业务执行完 commit half-message → broker 投递。**最终一致**。

### LLM 场景

Agent 多 tool 调用有"部分成功"问题——用户问 "查 USD/JPY 然后算 VaR"，第一步成功第二步失败 → 返回部分结果 + 说明哪步失败——**Saga 思想**。

---

## 6.4 CAP / BASE

**CAP 定理**：分布式系统三选二——Consistency 一致性 / Availability 可用性 / Partition tolerance 分区容错。**CAP 实际是 CP vs AP 二选一**（P 必然发生）。

| 类型 | 例子 |
|---|---|
| **CP** | Zookeeper / etcd / MongoDB（默认） |
| **AP** | Cassandra / DynamoDB / Redis Cluster |

**BASE 理论**（AP 的具体化）：
- **B**asically **A**vailable
- **S**oft state
- **E**ventually consistent

---

# 第 7 部分｜AI Agent 岗位特有议题

## 7.1 LLM API 配额与限流

### 一、LLM 限流的 3 层

**Layer 1：LLM 供应商限流**：DeepSeek / OpenAI 都有 rate limit——requests/min、tokens/min；超限返 429 + `Retry-After` 头

**Layer 2：我们应用层限流**：单 user 每秒 N 请求；全局保护 LLM 供应商配额不爆

**Layer 3：用户 quota**：按月 token 配额（如免费 100K / pro 1M）

### 二、响应 429 的标准做法

```python
from tenacity import retry, retry_if_exception_type, wait_exponential_jitter, stop_after_attempt

@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential_jitter(initial=1, max=60),
    stop=stop_after_attempt(5),
)
def call_llm(messages):
    try:
        return client.chat.completions.create(...)
    except openai.RateLimitError as e:
        retry_after = e.response.headers.get('Retry-After', 30)
        time.sleep(int(retry_after))
        raise
```

---

## 7.2 长任务管理（checkpoint + 断点续跑）

### 一、问题

我们项目 `MAX_TOOL_ROUNDS=2` 是短任务。但 Phase 5 复杂任务（10 步以上）需要：
- **断点续跑**：失败后从断点继续，不重头
- **状态持久化**：messages / tool_results 存 DB
- **可观测**：每步成功 / 失败可查

### 二、LangGraph checkpointer 方案

```python
from langgraph.checkpoint.sqlite import SqliteSaver

saver = SqliteSaver.from_conn_string("checkpoints.db")
graph = build_graph().compile(checkpointer=saver)

# 第一次跑
result = graph.invoke({"input": "..."}, config={"thread_id": "task_123"})

# 失败后从断点续跑
result = graph.invoke(None, config={"thread_id": "task_123"})
```

每步执行后 `saver` 把 state 写 DB。失败重启时从最近 checkpoint 恢复。

---

## 7.3 Streaming 后端架构

### 一、端到端 streaming 链路

```
LLM (DeepSeek SDK stream=True)
  ↓ 一 token 一推
Generator function (yield SSE chunks)
  ↓ HTTP chunked transfer
Nginx (proxy_buffering off)
  ↓ TCP push
浏览器 EventSource
  ↓ onmessage
React state update + rerender
```

**关键工程点**：
- LLM 调用必须 `stream=True`
- Generator 用 SSE 格式 `data: {...}\n\n`
- Nginx 必须 `proxy_buffering off`
- 浏览器用 `EventSource` 而非 `fetch`

### 二、流式中插入 trace 事件

我们项目独特之处——除了答案文本，还流式推送 trace（plan / tool_result / reflect）：

```python
yield f"data: {json.dumps({'trace': {'kind': 'plan', 'tools': [...]}})}\n\n"
# tool 执行
yield f"data: {json.dumps({'trace': {'kind': 'tool_result', 'name': ..., 'result': ...}})}\n\n"
# 答案文本
yield f"data: {json.dumps({'text': chunk})}\n\n"
```

前端实时展示 Agent 思考过程——**面试 demo 杀手锏**。

---

## 7.4 Multi-tenancy 隔离

**隔离 3 层**：

**1. 数据隔离**
- 每个 user_id 的对话历史独立存
- RAG 召回过滤 `user_id` metadata（如有用户私有 corpus）

**2. 计算隔离**
- 每用户 quota（token / requests / RAG 调用次数）
- 重用户限流更严

**3. 安全隔离**
- 不能让用户 A 看到用户 B 的对话
- Prompt injection 防御（我们 Phase 4.3）

---

## 7.5 LLM 成本可观测

### Token 计数 + 成本累计

每次 LLM 调用响应都有 `usage`：
```python
resp.usage.prompt_tokens
resp.usage.completion_tokens
```

我们 `observability.py` Langfuse 接入自动记录 `usage_details`。可以扩展为：
```python
TOKEN_PRICE = {
    "deepseek-chat": {"input": 0.001 / 1000, "output": 0.002 / 1000},
}

def calc_cost(model, usage):
    price = TOKEN_PRICE[model]
    return usage.prompt_tokens * price["input"] + usage.completion_tokens * price["output"]
```

写到 Prometheus metric / Langfuse trace / 业务 DB——可以按 user / 按时段聚合，做账单系统。

---

# 第 8 部分｜Java 补充（面 Java 岗用，可选读）

> **AI Agent 岗位很少深问 Java 八股**，但面阿里 / 字节后端混合岗时可能问。Python 出身的同学**了解原理 + 诚实说没深入实践**即可。

## 8.1 volatile / synchronized / Lock / AQS

### volatile
- **保证可见性 + 禁止重排序**
- **不保证原子性**（`count++` 即使 volatile 也不安全）
- 经典用例：单例 DCL 的 instance 字段

### synchronized
- 互斥锁，**保证可见性 + 原子性 + 禁止重排序**
- JDK 1.6 锁升级：偏向锁 → 轻量级锁 → 重量级锁

### ReentrantLock
- 替代 synchronized
- 可中断 / 可超时 / 公平锁可选 / 多 Condition

### AQS（AbstractQueuedSynchronizer）
- Java 并发包核心
- state（volatile int）+ CLH 队列（FIFO 双向链表）+ CAS
- ReentrantLock / Semaphore / CountDownLatch / ReadWriteLock 都基于 AQS

---

## 8.2 JVM 内存模型与 GC

### 内存区域
- **堆**：对象实例（GC 主要管这里）
- **方法区 / 元空间**：类元数据
- **虚拟机栈**：栈帧
- **程序计数器**：当前执行字节码位置

### GC 3 大算法
- **标记-清除**：碎片化
- **复制**：无碎片但 50% 浪费
- **标记-整理**：无碎片但慢

### G1（JDK 9+ 默认）
- 堆分 N region（1-32MB）
- 优先回收"垃圾最多 region"（Garbage First）
- 可设最大 STW 时间 `-XX:MaxGCPauseMillis=200`

### ZGC / Shenandoah（JDK 11/15+）
- 并发整理，STW < 10ms 甚至 < 1ms

### Python GC 对比
- Python 主要靠引用计数（ref_count 到 0 立即回收）
- 加分代标记-清除处理循环引用

---

## 8.3 ConcurrentHashMap 演进

**JDK 1.7**：Segment 分段锁——把 map 分 16 段，每段独立锁。并发度 16。

**JDK 1.8**：放弃 Segment，改 **CAS + synchronized 锁单个桶**。并发度 = 桶数（默认 16，扩容后变大）。

**为什么 1.8 改**：Segment 粒度还是太粗；锁桶粒度更细。

---

# 结语

这份指南总共 **8 大部分 + ~50 题**，每题都用 CompassFXPulse 项目作锚点举例。

**面试前 1 周复习路径**：
1. 第 2 / 3 部分（缓存 + 并发）—— **必背 100%**
2. 第 7 部分（AI Agent 特有）—— **差异化加分**
3. 第 4 / 6 部分（网络 + 架构）—— **80% 掌握**
4. 第 1 / 5 部分（DB + MQ）—— **60% 掌握**
5. 第 8 部分（Java）—— **了解原理即可**

**面试时的金句模板**：
- 被问后端原理 → "原理是 X，我们项目里 `app/xxx.py` 的实现是 Y，实测数字是 Z"
- 被问"你们做了 X 吗" → "当前没做，但理解原理：A B C；Phase 5 路线就是补这一块"
- 被问深挖追问 → 引用本指南"深挖追问 Q&A"段的具体回答

**最后一句**：八股不是要把所有名词都背下来，而是要做到"被任何角度追问都不慌"——本指南每题的 Q&A 段就是练这个的。
