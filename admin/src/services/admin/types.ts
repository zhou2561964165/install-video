export interface paths {
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 管理员登录
         * @description JSON邮箱/密码校验现有密码及AdminGrant/AccountControl；不存在用户也校验固定哑哈希，统一401。ADMIN_ALLOWED_ORIGINS为空拒绝写方法；限流429含约定JSON及X-Request-ID，包括外层中间件。替换当前浏览器旧管理会话，不接受普通Bearer。
         */
        post: operations["adminLogin"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 当前会话与开放权限集合
         * @description 实时校验session/AccountControl/AdminGrant，返回开放permission字符串。CSRF确定派生，GET不旋转，禁止日志。
         */
        get: operations["adminMe"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 撤销当前管理会话
         * @description 校验实时会话、Origin和X-CSRF-Token后服务器撤销并清cookie；重复使用已撤销或过期会话401也用相同ADMIN_COOKIE_PATH清cookie。客户端遇到任何401清内存会话、permissions、meta与CSRF并转登录。
         */
        post: operations["adminLogout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 有明确统计口径的真实概览
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminOverview"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 用户与权益列表
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminListUsers"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 用户、会员与UTC当日额度
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminGetUser"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users/{user_id}/access": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 账号启停（M2）
         * @description M1 feature未就绪返回503。M2同事务按稳定user_id顺序锁操作者/目标控制行及所需授权行，实时复核权限和自身/有效AdminGrant保护后才查幂等。CLI授撤目标管理员也先锁同目标控制行。保留期同actor/key/body重放在revision比较前返回原结果，异输入/结果过期409且墓碑阻止执行；新请求比expected_revision。真实enabled变更才增revision/auth_revision并撤销会话、同事务审计；no-op只审计。普通JWT新ar与实时控制检查先上线，无ar旧token拒绝，恢复后旧token不复活；未知结果禁止自动重发新key。 幂等固定operation=users.access，唯一(actor_user_id,operation,key)，请求指纹含规范化method/path/target_user_id/body；audit.action是结果，不参与scope。 指纹body只含规范化enabled、trim后reason、expected_revision；method/path/target同样参与，跨target重用同key为409，不是新操作。审计action区分users.access_enabled/disabled/noop/denied。
         */
        patch: operations["adminSetUserAccess"];
        trace?: never;
    };
    "/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 当前保留server Job列表
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminListJobs"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Job与安全成品详情
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminGetJob"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/memberships": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 持久会员行列表
         * @description 只列实际Membership行，effective由现有domain计算；用户详情无行另外投影free，不写行；主键user_id稳定排序。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminListMemberships"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/billing/checkouts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Checkout状态列表
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminListCheckouts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/billing/checkouts/{checkout_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Checkout逐事实详情
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminGetCheckout"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/billing/payments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Payment绑定与墓碑列表
         * @description id映射PI，不存在created_at/paid_at/amount。M1 billing_amounts.ready=false；future投影须已审同scope/livemode/PI绑定且所有可用verified amount_total/currency一致才known，否则unknown/conflicting且money=null；禁止按latest observed_at挑值或累加快照。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminListPayments"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/billing/payments/{payment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Payment可靠关联逐事实详情
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminGetPayment"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/audit/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 只读不可变审计
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminListAuditLogs"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/system/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 安全系统状态
         * @description 只读安全投影；每请求强鉴权，permission在服务端执行；基础只读不依赖可选feature，不调用第三方、不修复数据。 基础只读按x-permission授权，billing_amounts不影响支付记录页面；只有金额列另查该feature。
         */
        get: operations["adminSystemStatus"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/meta": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 安全元数据、集中策略与功能能力
         * @description 任何有效管理会话可读，无额外业务权限。features与auth/me capabilities及system capabilities同一投影；能力在请求时仍强制检查，不能信任前端缓存。
         */
        get: operations["adminMeta"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/support/tickets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 客服工单列表
         * @description 会员用户的工单与“会员付款后未到账”工单为priority；默认priority:desc即优先在前、同级按created_at升序、id兜底。
         */
        get: operations["adminListSupportTickets"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/support/tickets/{ticket_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 客服工单详情 */
        get: operations["adminGetSupportTicket"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/support/tickets/{ticket_id}/reply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 回复并结单
         * @description template_id只能是手选模板（不含reissued）；已结单409 ticket_closed。
         */
        post: operations["adminReplySupportTicket"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/support/tickets/{ticket_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** 驳回并结单 */
        post: operations["adminRejectSupportTicket"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/support/tickets/{ticket_id}/verify-payment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 向支付平台核实付款
         * @description 仅membership_not_credited；需订单有stripe会话、未履行、未超核实次数；支付平台不可达503 payment_provider_unavailable且不记录。
         */
        post: operations["adminVerifySupportPayment"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/support/tickets/{ticket_id}/reissue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 审核通过并补发会员
         * @description 同一事务行锁内复核：工单open且类型匹配、订单属于该用户且未履行、新鲜期内verified核实、付款未绑定他人或撤销、该订单未补发过。失败409（ticket_closed/not_reissuable_category/checkout_mismatch/already_fulfilled/not_verified/verification_stale/payment_conflict/membership_active/subscription_active/already_reissued）；会员仍由另一笔付款生效或绑定订阅时拒绝叠加补发。同key同工单重放返回原结果。
         */
        post: operations["adminReissueMembership"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users/{user_id}/membership": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 管理员设置会员权益
         * @description 实时校验会话、Origin、CSRF、memberships:write及membership_control_write。独立users.membership操作回执空间，key唯一，指纹含actor、method、path、target及规范化body；同key同指纹返回原membership/changed/audit_id/as_of，同key异操作者、body或目标拒绝409。按user、membership、control依次锁定，同事务变更、版本及审计；未知提交不得换key重试。手动控制不改付款事实，回调不能覆盖。
         */
        patch: operations["adminSetUserMembership"];
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** @description 不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。 */
        Id: string;
        Decimal: string;
        /** Format: date-time */
        UtcTime: string;
        /** Format: date-time */
        NullableUtcTime: string | null;
        /** @description admin独立异常形状，不改变普通API。detail含安全error_type/error/request_id，request_id为后台生成并与X-Request-ID响应头一致，审计记录沿用；422可有field_errors。不泄露堆栈或原始供应商响应，外层429也适配此形状。 */
        Error: {
            /** @description 安全投影字段 detail；精确语义见所属DTO说明。 */
            detail: {
                error_type: string;
                error: string;
                request_id: string;
                field_errors?: ({
                    field: string;
                    message: string;
                } & {
                    [key: string]: unknown;
                })[];
            } & {
                [key: string]: unknown;
            };
        } & {
            [key: string]: unknown;
        };
        /** @description 开放权限字符串集合；前端按已支持permission key判断，未知值不自动授权；服务端deny by default。 */
        Permission: string;
        Capability: {
            /** @description 安全投影字段 ready；精确语义见所属DTO说明。 */
            ready: boolean;
            /** @description 安全投影字段 reason；精确语义见所属DTO说明。 */
            reason: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 可选能力按权限及ready共同判定；membership_control_write仅控制管理员会员设置，未知能力默认关闭。 */
        Capabilities: {
            account_access_write: components["schemas"]["Capability"];
            billing_amounts: components["schemas"]["Capability"];
            support_reissue: components["schemas"]["Capability"];
            membership_control_write: components["schemas"]["Capability"];
        } & {
            [key: string]: unknown;
        };
        /** @description 仅返回实际会话到期时间；token由HttpOnly cookie管理，随后GET me获取permissions/CSRF。不返回普通JWT。 */
        SessionCreated: {
            /**
             * Format: date-time
             * @description 安全投影字段 session_expires_at；精确语义见所属DTO说明。
             */
            session_expires_at: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 每请求实时读取权限；CSRF由独立服务端密钥HMAC(session_id+token_hash+固定版本上下文)确定派生，GET不旋转，可重建、恒时验证，多标签页有效。 */
        AdminMe: {
            user_id: components["schemas"]["Id"];
            /**
             * Format: email
             * @description 安全投影字段 email；精确语义见所属DTO说明。
             */
            email: string;
            /** @description 仅展示角色标识，初始seed可扩展；禁止前端以role判断权限。 */
            role: string;
            /** @description 安全投影字段 permissions；精确语义见所属DTO说明。 */
            permissions: components["schemas"]["Permission"][];
            /**
             * Format: date-time
             * @description 安全投影字段 session_expires_at；精确语义见所属DTO说明。
             */
            session_expires_at: string;
            /** @description 仅客户端内存保存，禁止日志；确定派生而非不可恢复的hash；配置密钥不输出。 */
            csrf_token: string;
            capabilities: components["schemas"]["Capabilities"];
        } & {
            [key: string]: unknown;
        };
        LoginRequest: {
            /** Format: email */
            email: string;
            password: string;
        };
        /** @description 新增AccountControl安全投影；revision为账号控制版本，非会员版本；protected_account含当前操作者与任何有效AdminGrant账号。 */
        AccessControl: {
            /** @description 安全投影字段 enabled；精确语义见所属DTO说明。 */
            enabled: boolean;
            /** @description 安全投影字段 revision；精确语义见所属DTO说明。 */
            revision: string;
            /** @description 安全投影字段 protected_account；精确语义见所属DTO说明。 */
            protected_account: boolean;
        } & {
            [key: string]: unknown;
        };
        /** @description 沿现有额度domain读取；quota_day为请求事务DB时钟as_of的UTC日，unlimited仍计实际used，limit/remaining不限时null；不修改Quota/QuotaCharge。remaining=limit-used可为负，UI显示超出额度X并明示统计日，不截成0或修改used。 */
        Quota: {
            /**
             * Format: date
             * @description 安全投影字段 quota_day；精确语义见所属DTO说明。
             */
            quota_day: string;
            /** @description 安全投影字段 used；精确语义见所属DTO说明。 */
            used: number;
            /** @description 安全投影字段 limit；精确语义见所属DTO说明。 */
            limit: number | null;
            /** @description 安全投影字段 remaining；精确语义见所属DTO说明。 */
            remaining: number | null;
            /** @description 安全投影字段 unlimited；精确语义见所属DTO说明。 */
            unlimited: boolean;
        } & {
            [key: string]: unknown;
        };
        /** @description status/revision/expires_at保留付款记录语义。effective由管理员控制优先的统一策略按事务as_of计算；auto按原active且付款期限未到期；enabled为永久或独立管理员期限，到期不回落付款记录；disabled始终无效。无控制行等同auto/control_revision=0，无付款行仍可显示及管理。 */
        Membership: {
            user_id: components["schemas"]["Id"];
            /** @description 安全投影字段 status；精确语义见所属DTO说明。 */
            status: string;
            /** @description 安全投影字段 effective；精确语义见所属DTO说明。 */
            effective: boolean;
            /**
             * Format: date-time
             * @description 安全投影字段 expires_at；精确语义见所属DTO说明。
             */
            expires_at: string | null;
            /** @description 安全投影字段 revision；精确语义见所属DTO说明。 */
            revision: string | null;
            /** @description 安全投影字段 entitlement_source；精确语义见所属DTO说明。 */
            entitlement_source: string | null;
            /** @description 安全投影字段 cancel_at_period_end；精确语义见所属DTO说明。 */
            cancel_at_period_end: boolean;
            /** @enum {string} */
            control_mode: "auto" | "enabled" | "disabled";
            control_revision: string;
            /** Format: date-time */
            control_expires_at: string | null;
            /** @enum {string} */
            effective_reason: "payment_active" | "payment_expired" | "payment_inactive" | "admin_enabled" | "admin_expired" | "admin_disabled";
            /** Format: date-time */
            effective_expires_at: string | null;
            effective_permanent: boolean;
        } & {
            [key: string]: unknown;
        };
        /** @description 用户只读摘要；没有password_hash/token/cookie。会员沿domain服务投影，账号控制是本提案新增表，不冒充当前能力。 */
        UserSummary: {
            id: components["schemas"]["Id"];
            /**
             * Format: email
             * @description 安全投影字段 email；精确语义见所属DTO说明。
             */
            email: string;
            /**
             * Format: date-time
             * @description 安全投影字段 created_at；精确语义见所属DTO说明。
             */
            created_at: string;
            access: components["schemas"]["AccessControl"];
            membership: components["schemas"]["Membership"];
        } & {
            [key: string]: unknown;
        };
        UserDetail: {
            id: components["schemas"]["Id"];
            /**
             * Format: email
             * @description 安全投影字段 email；精确语义见所属DTO说明。
             */
            email: string;
            /**
             * Format: date-time
             * @description 安全投影字段 created_at；精确语义见所属DTO说明。
             */
            created_at: string;
            access: components["schemas"]["AccessControl"];
            membership: components["schemas"]["Membership"];
            quota: components["schemas"]["Quota"];
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        AccessPatch: {
            enabled: boolean;
            /** @description trim后Unicode码点计数；协议范围10..2000，运行默认10..500，由meta.limits给出，超运行边界422。 */
            reason: string;
            /** @description 非负十进制字符串，防止JS大整数精度损失。 */
            expected_revision: string;
        };
        /** @description 成功审计结果；原key/body在结果保留期重放原结果。no-op changed=false，不递增revision/auth_revision、不撤销会话。真实变更才递增并撤销。 */
        AccessResult: {
            user_id: components["schemas"]["Id"];
            /** @description 安全投影字段 enabled；精确语义见所属DTO说明。 */
            enabled: boolean;
            /** @description 安全投影字段 revision；精确语义见所属DTO说明。 */
            revision: string;
            audit_id: components["schemas"]["Id"];
            /** @description 安全投影字段 changed；精确语义见所属DTO说明。 */
            changed: boolean;
            /**
             * Format: date-time
             * @description 安全投影字段 recorded_at；精确语义见所属DTO说明。
             */
            recorded_at: string;
        } & {
            [key: string]: unknown;
        };
        /** @description legacy无manifest的字段保留null，不伪造verified；byte_size十进制字符串，不包含路径或下载URL。 */
        ArtifactSummary: {
            /** @description 安全投影字段 media_state；精确语义见所属DTO说明。 */
            media_state: string | null;
            /** @description 安全投影字段 byte_size；精确语义见所属DTO说明。 */
            byte_size: string | null;
            /** @description 安全投影字段 media_format；精确语义见所属DTO说明。 */
            media_format: string | null;
            /** @description 安全投影字段 media_check；精确语义见所属DTO说明。 */
            media_check: string | null;
            /**
             * Format: date-time
             * @description 安全投影字段 completed_at；精确语义见所属DTO说明。
             */
            completed_at: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 当前保留server Job安全投影；public_status与internal_state分开。来源仅host，不返回完整URL、query或凭据；不代表全部下载历史。 */
        JobSummary: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 user_id；精确语义见所属DTO说明。 */
            user_id: components["schemas"]["Id"] | null;
            /** @description 安全投影字段 title；精确语义见所属DTO说明。 */
            title: string | null;
            /** @description 由Job.url经urlsplit().hostname投影为小写hostname；不含userinfo、端口、路径或query，无法可靠提取时null。 */
            source_host: string | null;
            /**
             * @description 安全投影字段 execution_version；精确语义见所属DTO说明。
             * @enum {integer}
             */
            execution_version: 1 | 2;
            /** @description 安全投影字段 public_status；精确语义见所属DTO说明。 */
            public_status: string;
            /** @description 持久业务状态，legacy的NULL仍返回null；legacy_unset仅是列表查询伪值和overview分组名，不能作为response业务值。 */
            internal_state: string | null;
            /** @description 安全投影字段 progress；精确语义见所属DTO说明。 */
            progress: number;
            /** @description 安全投影字段 attempts_used；精确语义见所属DTO说明。 */
            attempts_used: number;
            /** @description 安全投影字段 attempts_limit；精确语义见所属DTO说明。 */
            attempts_limit: number;
            /**
             * Format: date-time
             * @description 安全投影字段 created_at；精确语义见所属DTO说明。
             */
            created_at: string;
            /**
             * Format: date-time
             * @description 安全投影字段 updated_at；精确语义见所属DTO说明。
             */
            updated_at: string;
        } & {
            [key: string]: unknown;
        };
        AttemptSummary: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 attempt_index；精确语义见所属DTO说明。 */
            attempt_index: number;
            /** @description 安全投影字段 state；精确语义见所属DTO说明。 */
            state: string;
            /**
             * Format: date-time
             * @description 安全投影字段 started_at；精确语义见所属DTO说明。
             */
            started_at: string;
            /**
             * Format: date-time
             * @description 安全投影字段 ended_at；精确语义见所属DTO说明。
             */
            ended_at: string | null;
            /** @description 安全投影字段 error_code；精确语义见所属DTO说明。 */
            error_code: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 只读Job与尝试安全摘要；无取消/重试。error_message仅由error_type固定安全映射，未知类型通用文案，永不透传Job.error。成品不返回绝对路径、签名URL、owner或lease token。 */
        JobDetail: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 user_id；精确语义见所属DTO说明。 */
            user_id: components["schemas"]["Id"] | null;
            /** @description 安全投影字段 title；精确语义见所属DTO说明。 */
            title: string | null;
            /** @description 由Job.url经urlsplit().hostname投影为小写hostname；不含userinfo、端口、路径或query，无法可靠提取时null。 */
            source_host: string | null;
            /**
             * @description 安全投影字段 execution_version；精确语义见所属DTO说明。
             * @enum {integer}
             */
            execution_version: 1 | 2;
            /** @description 安全投影字段 public_status；精确语义见所属DTO说明。 */
            public_status: string;
            /** @description 持久业务状态，legacy的NULL仍返回null；legacy_unset仅是列表查询伪值和overview分组名，不能作为response业务值。 */
            internal_state: string | null;
            /** @description 安全投影字段 progress；精确语义见所属DTO说明。 */
            progress: number;
            /** @description 安全投影字段 attempts_used；精确语义见所属DTO说明。 */
            attempts_used: number;
            /** @description 安全投影字段 attempts_limit；精确语义见所属DTO说明。 */
            attempts_limit: number;
            /**
             * Format: date-time
             * @description 安全投影字段 created_at；精确语义见所属DTO说明。
             */
            created_at: string;
            /**
             * Format: date-time
             * @description 安全投影字段 updated_at；精确语义见所属DTO说明。
             */
            updated_at: string;
            /**
             * Format: date-time
             * @description 安全投影字段 expires_at；精确语义见所属DTO说明。
             */
            expires_at: string | null;
            /**
             * Format: date-time
             * @description 安全投影字段 run_deadline_at；精确语义见所属DTO说明。
             */
            run_deadline_at: string | null;
            /**
             * Format: date-time
             * @description 安全投影字段 next_run_at；精确语义见所属DTO说明。
             */
            next_run_at: string | null;
            /** @description 安全投影字段 error_type；精确语义见所属DTO说明。 */
            error_type: string | null;
            /** @description 仅由error_type映射固定安全文案；未知类型用通用文案，无错误时可null。永不透传Job.error或原始异常文本。 */
            error_message: string | null;
            artifact: components["schemas"]["ArtifactSummary"];
            /** @description 安全投影字段 attempts；精确语义见所属DTO说明。 */
            attempts: components["schemas"]["AttemptSummary"][];
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 非负最小货币单位十进制字符串；currency仅保留原事实符合小写三字母正则的值，不改大小写修复事实，不合规时外层money=null。历史未知金额/币种/指数保留null，不按9.9、当前Price或latest observed_at回填，不改事实；不是营收投影。 */
        Money: {
            /** @description 安全投影字段 amount_minor；精确语义见所属DTO说明。 */
            amount_minor: string | null;
            /** @description 安全投影字段 currency；精确语义见所属DTO说明。 */
            currency: string | null;
            /** @description 来自权威币种元数据；M1无权威来源恒为null，不默认2。 */
            currency_exponent: number | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 仅verified逐事件快照，observed_at不是付款时间；同一付款多快照不能相加。历史金额/币种/指数未知保留null，不取latest或现价补齐，不修改事实；amount_refunded_minor只表示此事实，不代表当前累计退款。 */
        BillingFactSnapshot: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 provider_account_scope；精确语义见所属DTO说明。 */
            provider_account_scope: string;
            /** @description 安全投影字段 livemode；精确语义见所属DTO说明。 */
            livemode: boolean | null;
            /**
             * @description 安全投影字段 reconciliation；精确语义见所属DTO说明。
             * @constant
             */
            reconciliation: "verified";
            /** @description 安全投影字段 provider_status；精确语义见所属DTO说明。 */
            provider_status: string | null;
            /** @description 原事实币种不符合小写三字母正则时null；未知字段保持null，M1 currency_exponent恒null，不回填历史事实。 */
            money: components["schemas"]["Money"] | null;
            /** @description 安全投影字段 amount_refunded_minor；精确语义见所属DTO说明。 */
            amount_refunded_minor: string | null;
            /**
             * Format: date-time
             * @description 安全投影字段 observed_at；精确语义见所属DTO说明。
             */
            observed_at: string;
        } & {
            [key: string]: unknown;
        };
        /** @description Checkout state/reconciliation/fulfilled独立，不等于付款成功；不返回url/create_payload/供应商原始载荷。 */
        CheckoutSummary: {
            id: components["schemas"]["Id"];
            user_id: components["schemas"]["Id"];
            /** @description 当前源码已知pending/open/paid/expired/failed；paid不是fulfilled/reconciliation同义词；未知值中性显示，不能改名completed。 */
            state: string;
            /** @description 安全投影字段 reconciliation；精确语义见所属DTO说明。 */
            reconciliation: string | null;
            /** @description 安全投影字段 fulfilled；精确语义见所属DTO说明。 */
            fulfilled: boolean;
            /** @description 安全投影字段 provider_account_scope；精确语义见所属DTO说明。 */
            provider_account_scope: string | null;
            /** @description 安全投影字段 livemode；精确语义见所属DTO说明。 */
            livemode: boolean | null;
            /**
             * Format: date-time
             * @description 安全投影字段 created_at；精确语义见所属DTO说明。
             */
            created_at: string;
            /**
             * Format: date-time
             * @description 安全投影字段 expires_at；精确语义见所属DTO说明。
             */
            expires_at: string | null;
            /** @description 安全投影字段 revision；精确语义见所属DTO说明。 */
            revision: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 只查checkout_id且scope/livemode匹配的verified事实。scope未知或关联歧义不联接，不触发对账或外部GET。 */
        CheckoutDetail: {
            id: components["schemas"]["Id"];
            user_id: components["schemas"]["Id"];
            /** @description 当前源码已知pending/open/paid/expired/failed；paid不是fulfilled/reconciliation同义词；未知值中性显示，不能改名completed。 */
            state: string;
            /** @description 安全投影字段 reconciliation；精确语义见所属DTO说明。 */
            reconciliation: string | null;
            /** @description 安全投影字段 fulfilled；精确语义见所属DTO说明。 */
            fulfilled: boolean;
            /** @description 安全投影字段 provider_account_scope；精确语义见所属DTO说明。 */
            provider_account_scope: string | null;
            /** @description 安全投影字段 livemode；精确语义见所属DTO说明。 */
            livemode: boolean | null;
            /**
             * Format: date-time
             * @description 安全投影字段 created_at；精确语义见所属DTO说明。
             */
            created_at: string;
            /**
             * Format: date-time
             * @description 安全投影字段 expires_at；精确语义见所属DTO说明。
             */
            expires_at: string | null;
            /** @description 安全投影字段 revision；精确语义见所属DTO说明。 */
            revision: string;
            /** @description 安全投影字段 price_id；精确语义见所属DTO说明。 */
            price_id: string;
            /** @description 安全投影字段 mode；精确语义见所属DTO说明。 */
            mode: string;
            /** @description 安全投影字段 duration_days；精确语义见所属DTO说明。 */
            duration_days: number;
            /** @description 安全投影字段 reconcile_attempts；精确语义见所属DTO说明。 */
            reconcile_attempts: number;
            /** @description 安全投影字段 verified_facts；精确语义见所属DTO说明。 */
            verified_facts: components["schemas"]["BillingFactSnapshot"][];
            /**
             * @description 安全投影字段 facts_state；精确语义见所属DTO说明。
             * @enum {string}
             */
            facts_state: "available" | "none" | "ambiguous";
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description id映射BillingPayment.payment_intent，现表只有PI绑定/source_id/user_id/revoked。M1 billing_amounts.ready=false，money与amount_source=null且amount_state=unknown；DTO预留以后经审金额投影，无paid_at/created_at猜测。 */
        PaymentSummary: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 user_id；精确语义见所属DTO说明。 */
            user_id: components["schemas"]["Id"] | null;
            /** @description 安全投影字段 source_id；精确语义见所属DTO说明。 */
            source_id: string | null;
            /** @description 安全投影字段 revoked；精确语义见所属DTO说明。 */
            revoked: boolean;
            money: components["schemas"]["Money"] | null;
            /** @description M1为unknown；能力关闭时不展示金额列。未来已审权威投影才可known，冲突conflicting且money=null。 */
            amount_state: string;
            /** @description M1为null；未来已审可靠来源标识，不能由客户端猜测。 */
            amount_source: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 先检查所有同payment_intent候选事实，不先过滤掉跨user或跨scope/livemode冲突。仅Payment.user_id非空、所有候选user_id与之相等、且候选只构成唯一且明确的(provider_account_scope,livemode)组，并有reconciliation=verified事实时available，只列该组verified事实。无同PI候选或无verified为none；存在候选但user为空/不一致、跨组或组信息不明为ambiguous且优先于none，此时verified_facts=[]并给安全原因。裸PI不足，不选latest observed_at、不累加、不推paid_at或营收；退款只逐事实展示。 */
        PaymentDetail: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 user_id；精确语义见所属DTO说明。 */
            user_id: components["schemas"]["Id"] | null;
            /** @description 安全投影字段 source_id；精确语义见所属DTO说明。 */
            source_id: string | null;
            /** @description 安全投影字段 revoked；精确语义见所属DTO说明。 */
            revoked: boolean;
            money: components["schemas"]["Money"] | null;
            /** @description M1为unknown；能力关闭时不展示金额列。未来已审权威投影才可known，冲突conflicting且money=null。 */
            amount_state: string;
            /** @description 安全投影字段 verified_facts；精确语义见所属DTO说明。 */
            verified_facts: components["schemas"]["BillingFactSnapshot"][];
            /**
             * @description 安全投影字段 facts_state；精确语义见所属DTO说明。
             * @enum {string}
             */
            facts_state: "available" | "none" | "ambiguous";
            /** @description 安全投影字段 facts_reason；精确语义见所属DTO说明。 */
            facts_reason: string | null;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
            /** @description M1为null；未来已审可靠来源标识，不能由客户端猜测。 */
            amount_source: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description append-only安全审计，不输出password/token/cookie/完整请求/原始IP/指纹。启停固定幂等operation=users.access；唯一(actor_user_id,operation,key)，跨target同key冲突。action单独表达enabled/disabled/noop/denied结果，不参与幂等scope。 */
        AuditEntry: {
            id: components["schemas"]["Id"];
            /** @description 安全投影字段 actor_user_id；精确语义见所属DTO说明。 */
            actor_user_id: components["schemas"]["Id"] | null;
            /** @description 安全投影字段 target_user_id；精确语义见所属DTO说明。 */
            target_user_id: components["schemas"]["Id"] | null;
            /** @description 安全投影字段 action；精确语义见所属DTO说明。 */
            action: string;
            /** @description 安全投影字段 outcome；精确语义见所属DTO说明。 */
            outcome: string;
            /** @description 安全投影字段 reason；精确语义见所属DTO说明。 */
            reason: string | null;
            /** @description 安全投影字段 request_id；精确语义见所属DTO说明。 */
            request_id: string;
            /**
             * Format: date-time
             * @description 安全投影字段 recorded_at；精确语义见所属DTO说明。
             */
            recorded_at: string;
            /** @description 安全投影字段 change；精确语义见所属DTO说明。 */
            change: components["schemas"]["AuditChange"] | null;
            /** @description 幂等操作标识，启停固定users.access；登录/退出等非该操作为null。与结果action分离。 */
            operation: string | null;
        } & {
            [key: string]: unknown;
        };
        AuditChange: components["schemas"]["AccessAuditChange"] | components["schemas"]["MembershipAuditChange"];
        StateCount: {
            /** @description 安全投影字段 state；精确语义见所属DTO说明。 */
            state: string;
            /** @description 安全投影字段 count；精确语义见所属DTO说明。 */
            count: number;
        } & {
            [key: string]: unknown;
        };
        /** @description 只统计所有用户、有效VIP、当前保留server Job；不是全部下载次数或营收。legacy internal_state=null以legacy_unset分组，仅显示不写回。 */
        Overview: {
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
            /** @description 安全投影字段 users_total；精确语义见所属DTO说明。 */
            users_total: number;
            /** @description 安全投影字段 effective_vip_total；精确语义见所属DTO说明。 */
            effective_vip_total: number;
            /** @description 安全投影字段 retained_server_jobs_total；精确语义见所属DTO说明。 */
            retained_server_jobs_total: number;
            /** @description 安全投影字段 jobs_by_public_status；精确语义见所属DTO说明。 */
            jobs_by_public_status: components["schemas"]["StateCount"][];
            /** @description 安全投影字段 jobs_by_internal_state；精确语义见所属DTO说明。 */
            jobs_by_internal_state: components["schemas"]["StateCount"][];
            /** @description 安全投影字段 scope；精确语义见所属DTO说明。 */
            scope: {
                users: string;
                effective_vip: string;
                jobs: string;
            } & {
                [key: string]: unknown;
            };
        } & {
            [key: string]: unknown;
        };
        /** @description 当前M1无可靠采样的download_worker/billing_worker/artifact_store仅unknown、reason_code=no_reliable_sample、checked_at=null；database仅可据本次只读查询成功为ok。不由HTTP200或进程存在猜健康，不返回地址、路径、配置或key。 */
        ComponentStatus: {
            /**
             * @description 安全投影字段 component；精确语义见所属DTO说明。
             * @enum {string}
             */
            component: "database" | "download_worker" | "billing_worker" | "artifact_store";
            /**
             * @description 安全投影字段 status；精确语义见所属DTO说明。
             * @enum {string}
             */
            status: "ok" | "degraded" | "unavailable" | "unknown";
            /** @description 安全投影字段 reason_code；精确语义见所属DTO说明。 */
            reason_code: string | null;
            /**
             * Format: date-time
             * @description 安全投影字段 checked_at；精确语义见所属DTO说明。
             */
            checked_at: string | null;
        } & {
            [key: string]: unknown;
        };
        /** @description 只读现有安全采样；不探测第三方/编辑配置/重启。PG普通download仍503时download_submission_ready.ready=false。 */
        SystemStatus: {
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
            /** @description 安全投影字段 components；精确语义见所属DTO说明。 */
            components: components["schemas"]["ComponentStatus"][];
            capabilities: components["schemas"]["Capabilities"];
            download_submission_ready: components["schemas"]["Capability"];
        } & {
            [key: string]: unknown;
        };
        /**
         * @description 分页安全投影；items/total同一只读一致快照，as_of为UTC；超范围页items为空，跨页非冻结。响应可新增可选字段，客户端pick已支持字段。 example完全虚构，不是实际账号或验收证据。
         * @example {
         *       "items": [
         *         {
         *           "id": "usr_example_01",
         *           "email": "synthetic-admin@example.invalid",
         *           "created_at": "2026-10-01T00:00:00Z",
         *           "access": {
         *             "enabled": true,
         *             "revision": "0",
         *             "protected_account": false
         *           },
         *           "membership": {
         *             "user_id": "usr_example_01",
         *             "status": "free",
         *             "effective": false,
         *             "expires_at": null,
         *             "revision": null,
         *             "entitlement_source": null,
         *             "cancel_at_period_end": false,
         *             "control_mode": "auto",
         *             "control_revision": "0",
         *             "control_expires_at": null,
         *             "effective_reason": "payment_inactive",
         *             "effective_expires_at": null,
         *             "effective_permanent": false
         *           }
         *         }
         *       ],
         *       "total": 1,
         *       "page": 1,
         *       "page_size": 20,
         *       "as_of": "2026-10-26T00:00:00Z"
         *     }
         */
        UserPage: {
            /** @description 安全投影字段 items；精确语义见所属DTO说明。 */
            items: components["schemas"]["UserSummary"][];
            /** @description 安全投影字段 total；精确语义见所属DTO说明。 */
            total: number;
            /** @description 安全投影字段 page；精确语义见所属DTO说明。 */
            page: number;
            /** @description 安全投影字段 page_size；精确语义见所属DTO说明。 */
            page_size: number;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 分页安全投影；items/total同一只读一致快照，as_of为UTC；超范围页items为空，跨页非冻结。响应可新增可选字段，客户端pick已支持字段。 */
        JobPage: {
            /** @description 安全投影字段 items；精确语义见所属DTO说明。 */
            items: components["schemas"]["JobSummary"][];
            /** @description 安全投影字段 total；精确语义见所属DTO说明。 */
            total: number;
            /** @description 安全投影字段 page；精确语义见所属DTO说明。 */
            page: number;
            /** @description 安全投影字段 page_size；精确语义见所属DTO说明。 */
            page_size: number;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 分页安全投影；items/total同一只读一致快照，as_of为UTC；超范围页items为空，跨页非冻结。响应可新增可选字段，客户端pick已支持字段。 */
        MembershipPage: {
            /** @description 安全投影字段 items；精确语义见所属DTO说明。 */
            items: components["schemas"]["Membership"][];
            /** @description 安全投影字段 total；精确语义见所属DTO说明。 */
            total: number;
            /** @description 安全投影字段 page；精确语义见所属DTO说明。 */
            page: number;
            /** @description 安全投影字段 page_size；精确语义见所属DTO说明。 */
            page_size: number;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 分页安全投影；items/total同一只读一致快照，as_of为UTC；超范围页items为空，跨页非冻结。响应可新增可选字段，客户端pick已支持字段。 */
        CheckoutPage: {
            /** @description 安全投影字段 items；精确语义见所属DTO说明。 */
            items: components["schemas"]["CheckoutSummary"][];
            /** @description 安全投影字段 total；精确语义见所属DTO说明。 */
            total: number;
            /** @description 安全投影字段 page；精确语义见所属DTO说明。 */
            page: number;
            /** @description 安全投影字段 page_size；精确语义见所属DTO说明。 */
            page_size: number;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 分页安全投影；items/total同一只读一致快照，as_of为UTC；超范围页items为空，跨页非冻结。响应可新增可选字段，客户端pick已支持字段。 */
        PaymentPage: {
            /** @description 安全投影字段 items；精确语义见所属DTO说明。 */
            items: components["schemas"]["PaymentSummary"][];
            /** @description 安全投影字段 total；精确语义见所属DTO说明。 */
            total: number;
            /** @description 安全投影字段 page；精确语义见所属DTO说明。 */
            page: number;
            /** @description 安全投影字段 page_size；精确语义见所属DTO说明。 */
            page_size: number;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 分页安全投影；items/total同一只读一致快照，as_of为UTC；超范围页items为空，跨页非冻结。响应可新增可选字段，客户端pick已支持字段。 */
        AuditPage: {
            /** @description 安全投影字段 items；精确语义见所属DTO说明。 */
            items: components["schemas"]["AuditEntry"][];
            /** @description 安全投影字段 total；精确语义见所属DTO说明。 */
            total: number;
            /** @description 安全投影字段 page；精确语义见所属DTO说明。 */
            page: number;
            /** @description 安全投影字段 page_size；精确语义见所属DTO说明。 */
            page_size: number;
            /**
             * Format: date-time
             * @description 安全投影字段 as_of；精确语义见所属DTO说明。
             */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 服务端配置的运行值；reason_min<=reason_max；刷新0或15..300，隐藏页暂停；幂等结果至少7天默认30天，之后保留不可复用key墓碑。安全约束不可由前端放宽。 */
        PolicyLimits: {
            /** @default 900 */
            session_ttl_seconds: number;
            /** @default 10 */
            reason_min_length: number;
            /** @default 500 */
            reason_max_length: number;
            /** @default 2592000 */
            idempotency_replay_retention_seconds: number;
            /**
             * @description 0为手动；非零15..300秒，隐藏页面暂停，不自动重发写操作。
             * @default 0
             */
            refresh_interval_seconds: 0 | number;
        } & {
            [key: string]: unknown;
        };
        /** @description default_page_size<=max_page_size，所有列表运行最大值由此投影。协议上限1000，超运行值422；前端不能自行放宽。 */
        PaginationPolicy: {
            /** @constant */
            default_page: 1;
            /** @default 20 */
            default_page_size: number;
            /** @default 100 */
            max_page_size: number;
        } & {
            [key: string]: unknown;
        };
        /** @description 只为显示提供安全标签；客户端只接受预定义tone，不执行返回内容。未知value中性回退。 */
        StateDisplay: {
            value: string;
            label: string;
            /** @enum {string} */
            tone: "neutral" | "info" | "success" | "warning" | "error";
        } & {
            [key: string]: unknown;
        };
        /** @description 仅预定义领域键，如job.public_status、job.internal_state、membership.status、checkout.state。开放value用于兼容状态扩展，不改业务状态语义。 */
        StateDictionary: {
            domain: string;
            values: components["schemas"]["StateDisplay"][];
        } & {
            [key: string]: unknown;
        };
        /** @description name必须是该resource契约已支持的查询参数；enum按allowed_values交集，boolean/text/id/datetime按契约schema校验，无有限值白名单。不得生成任意SQL。 */
        FilterDescriptor: ({
            name: string;
            /** @description 仅kind=enum时必须提供，客户端取契约枚举与此值交集；其他kind不提供，禁止列真实账号/ID白名单。 */
            allowed_values?: string[];
            /** @enum {string} */
            kind: "enum" | "boolean" | "text" | "id" | "datetime";
        } & {
            [key: string]: unknown;
        }) & unknown;
        /** @description resource为受支持列表operationId；sort_values取契约与服务器交集，filters为安全参数白名单，不含分页/sort。未知name/kind不自动渲染，服务端校验失败422。 */
        ResourceQuery: {
            resource: string;
            sort_values: string[];
            filters: components["schemas"]["FilterDescriptor"][];
        } & {
            [key: string]: unknown;
        };
        /**
         * @description 所有有效管理会话可读，不额外要求业务权限。基础只读菜单/GET按permission；账号启停、会员设置与金额列额外按各自features。只返回安全显示元数据，不返回密钥、账号/ID白名单或动态规则。 example完全合成、不是运行配置或验收证据；实际queries列出所有受支持resource/filters/sorts。
         * @example {
         *       "api_version": "v1",
         *       "contract_version": "1.0.0-proposal.20261029.1",
         *       "as_of": "2026-10-26T00:00:00Z",
         *       "features": {
         *         "account_access_write": {
         *           "ready": false,
         *           "reason": "M2尚未实施"
         *         },
         *         "billing_amounts": {
         *           "ready": false,
         *           "reason": "金额投影尚未验收"
         *         },
         *         "support_reissue": {
         *           "ready": false,
         *           "reason": "合成示例不开放支付核查"
         *         },
         *         "membership_control_write": {
         *           "ready": false,
         *           "reason": "合成示例不执行会员设置"
         *         }
         *       },
         *       "pagination": {
         *         "default_page": 1,
         *         "default_page_size": 20,
         *         "max_page_size": 100
         *       },
         *       "display_timezone": "Asia/Singapore",
         *       "quota_day_timezone": "UTC",
         *       "quota_day_semantics": "accepted_at_utc_date",
         *       "limits": {
         *         "session_ttl_seconds": 900,
         *         "reason_min_length": 10,
         *         "reason_max_length": 500,
         *         "idempotency_replay_retention_seconds": 2592000,
         *         "refresh_interval_seconds": 0
         *       },
         *       "queries": [
         *         {
         *           "resource": "adminListUsers",
         *           "sort_values": [
         *             "created_at:desc",
         *             "email:asc"
         *           ],
         *           "filters": [
         *             {
         *               "name": "email",
         *               "kind": "text"
         *             },
         *             {
         *               "name": "enabled",
         *               "kind": "boolean"
         *             }
         *           ]
         *         },
         *         {
         *           "resource": "adminListJobs",
         *           "sort_values": [
         *             "created_at:desc"
         *           ],
         *           "filters": [
         *             {
         *               "name": "user_id",
         *               "kind": "id"
         *             },
         *             {
         *               "name": "public_status",
         *               "kind": "enum",
         *               "allowed_values": [
         *                 "queued",
         *                 "downloading",
         *                 "merging",
         *                 "done",
         *                 "error"
         *               ]
         *             },
         *             {
         *               "name": "internal_state",
         *               "kind": "enum",
         *               "allowed_values": [
         *                 "queued",
         *                 "running",
         *                 "retry_wait",
         *                 "succeeded",
         *                 "failed",
         *                 "needs_review",
         *                 "legacy_hold",
         *                 "legacy_unset"
         *               ]
         *             }
         *           ]
         *         },
         *         {
         *           "resource": "adminListCheckouts",
         *           "sort_values": [
         *             "created_at:desc"
         *           ],
         *           "filters": [
         *             {
         *               "name": "state",
         *               "kind": "enum",
         *               "allowed_values": [
         *                 "pending",
         *                 "open",
         *                 "paid",
         *                 "expired",
         *                 "failed"
         *               ]
         *             }
         *           ]
         *         },
         *         {
         *           "resource": "adminListAuditLogs",
         *           "sort_values": [
         *             "recorded_at:desc"
         *           ],
         *           "filters": [
         *             {
         *               "name": "recorded_from",
         *               "kind": "datetime"
         *             }
         *           ]
         *         }
         *       ],
         *       "state_dictionaries": [
         *         {
         *           "domain": "job.public_status",
         *           "values": [
         *             {
         *               "value": "done",
         *               "label": "已完成",
         *               "tone": "success"
         *             }
         *           ]
         *         }
         *       ]
         *     }
         */
        AdminMeta: {
            /** @description 当前主版本，例如v1；破坏性变更走v2。 */
            api_version: string;
            /** @description 对应冻结契约修订版本。 */
            contract_version: string;
            /** @description 请求只读事务DB时钟的UTC ISO8601时间，非空且以Z结尾。 */
            as_of: components["schemas"]["UtcTime"];
            features: components["schemas"]["Capabilities"];
            pagination: components["schemas"]["PaginationPolicy"];
            /** @description 服务端安全配置的IANA显示时区；存储/接口仍UTC，不影响quota_day。 */
            display_timezone: string;
            /** @constant */
            quota_day_timezone: "UTC";
            /**
             * @description PG受理扣额以DownloadOperation.accepted_at的UTC日期冻结，重放不移日；用户今日额度投影取请求事务DB时钟as_of的UTC日期。
             * @constant
             */
            quota_day_semantics: "accepted_at_utc_date";
            limits: components["schemas"]["PolicyLimits"];
            queries: components["schemas"]["ResourceQuery"][];
            state_dictionaries: components["schemas"]["StateDictionary"][];
        } & {
            [key: string]: unknown;
        };
        SupportAction: {
            allowed: boolean;
            reason: string | null;
        } & {
            [key: string]: unknown;
        };
        SupportActions: {
            verify: components["schemas"]["SupportAction"];
            reissue: components["schemas"]["SupportAction"];
            reply: components["schemas"]["SupportAction"];
            reject: components["schemas"]["SupportAction"];
        } & {
            [key: string]: unknown;
        };
        PaymentCheck: {
            result: string;
            checked_at: components["schemas"]["UtcTime"];
            fresh: boolean;
        } & {
            [key: string]: unknown;
        };
        SupportTicketSummary: {
            id: components["schemas"]["Id"];
            user_id: components["schemas"]["Id"];
            user_email: string;
            category: string;
            category_label: string;
            priority: string;
            state: string;
            resolution: string | null;
            checkout_id: string | null;
            created_at: components["schemas"]["UtcTime"];
            resolved_at: components["schemas"]["NullableUtcTime"];
        } & {
            [key: string]: unknown;
        };
        SupportTicketDetail: {
            id: components["schemas"]["Id"];
            user_id: components["schemas"]["Id"];
            user_email: string;
            category: string;
            category_label: string;
            priority: string;
            state: string;
            resolution: string | null;
            checkout_id: string | null;
            created_at: components["schemas"]["UtcTime"];
            resolved_at: components["schemas"]["NullableUtcTime"];
            /** @description 用户填写的纯文本，客户端必须按文本渲染。 */
            user_note: string | null;
            reply_template: string | null;
            reply_text: string | null;
            reply_note: string | null;
            resolved_by: string | null;
            checkout: components["schemas"]["CheckoutSummary"] | null;
            membership: components["schemas"]["Membership"];
            latest_check: components["schemas"]["PaymentCheck"] | null;
            actions: components["schemas"]["SupportActions"];
            as_of: components["schemas"]["UtcTime"];
        } & {
            [key: string]: unknown;
        };
        SupportTicketPage: {
            items: components["schemas"]["SupportTicketSummary"][];
            total: number;
            page: number;
            page_size: number;
            as_of: components["schemas"]["UtcTime"];
        } & {
            [key: string]: unknown;
        };
        SupportReply: {
            template_id: string;
            note?: string | null;
        };
        SupportTicketState: {
            id: components["schemas"]["Id"];
            state: string;
            resolution: string | null;
        } & {
            [key: string]: unknown;
        };
        ReissueResult: {
            ticket_id: components["schemas"]["Id"];
            granted_days: number;
            expires_at: components["schemas"]["UtcTime"];
            reply_text: string;
        } & {
            [key: string]: unknown;
        };
        /** @description 仅enabled允许期限，null表示永久；指定期限必须晚于事务时钟；auto/disabled要求null。原因trim后校验，expected_revision为独立control_revision。 */
        MembershipPatch: {
            /** @enum {string} */
            mode: "auto" | "enabled" | "disabled";
            /** Format: date-time */
            expires_at: string | null;
            reason: string;
            expected_revision: string;
        };
        MembershipResult: {
            membership: components["schemas"]["Membership"];
            changed: boolean;
            audit_id: components["schemas"]["Id"];
            /** Format: date-time */
            as_of: string;
        } & {
            [key: string]: unknown;
        };
        AccessAuditChange: {
            /** @description 安全投影字段 enabled_before；精确语义见所属DTO说明。 */
            enabled_before: boolean;
            /** @description 安全投影字段 enabled_after；精确语义见所属DTO说明。 */
            enabled_after: boolean;
            /** @description 安全投影字段 revision_before；精确语义见所属DTO说明。 */
            revision_before: string;
            /** @description 安全投影字段 revision_after；精确语义见所属DTO说明。 */
            revision_after: string;
        } & {
            [key: string]: unknown;
        };
        MembershipAuditChange: {
            /** @enum {string} */
            control_mode_before: "auto" | "enabled" | "disabled";
            /** @enum {string} */
            control_mode_after: "auto" | "enabled" | "disabled";
            /** Format: date-time */
            control_expires_at_before: string | null;
            /** Format: date-time */
            control_expires_at_after: string | null;
            control_revision_before: string;
            control_revision_after: string;
        } & {
            [key: string]: unknown;
        };
    };
    responses: {
        /** @description 401：未认证、过期或撤销；login统一失败。客户端清内存会话、permissions、meta与CSRF后转登录；logout额外清同Path cookie。 */
        Unauthorized: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 403：权限/Origin/CSRF不符或protected_account。 */
        Forbidden: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 404：资源不存在。 */
        NotFound: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 409：revision_changed、idempotency_conflict或idempotency_result_expired；不重复执行。 */
        Conflict: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 422：输入/过滤器/运行限制不合法，安全field_errors。 */
        ValidationError: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 429：限流；按Retry-After等待，不自动重发写操作。包括在admin子应用之前生效的全局中间件，也须返回本JSON错误形状与X-Request-ID。 */
        TooManyRequests: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                /** @description 可选等待秒数；不是自动重发写请求的许可。 */
                "Retry-After"?: number;
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 503：服务/能力未就绪，写结果可能未知，不自动更换key。 */
        Unavailable: {
            headers: {
                "X-Request-ID": components["headers"]["RequestId"];
                /** @description 可选等待秒数；不是自动重发写请求的许可。 */
                "Retry-After"?: number;
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        /** @description 页码，默认1。 */
        Page: number;
        /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
        PageSize: number;
        /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
        Csrf: string;
        /** @description 16..128 ASCII字符，各operation使用独立幂等空间，具体作用域见operation说明。账号启停保留actor_user_id+users.access+key作用域；会员控制使用users.membership独立回执，key唯一且指纹包含操作者、method、path、target及规范化body，跨操作者、目标或body复用会员key均409。指纹与审计结果action独立。默认保留结果30天至少7天，之后墓碑不可复用，不自动更换。 */
        IdempotencyKey: string;
    };
    requestBodies: never;
    headers: {
        /** @description Backend generated request UUID; identical to error detail.request_id and audit request_id. */
        RequestId: string;
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    adminLogin: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    /** @description iv_admin_session=<opaque>; HttpOnly; Secure; SameSite=Strict; Path=<显式ADMIN_COOKIE_PATH>; Max-Age=<配置TTL>。Path不从请求推断，配置缺失503；默认TTL900秒，明确dev HTTP可Secure=false。 */
                    "Set-Cookie"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionCreated"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminMe: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminMe"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminLogout: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 会话已撤销并清相同Path的cookie，无响应体。 */
            204: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    /** @description 同名、相同部署Path cookie Max-Age=0；服务端同时撤销。 */
                    "Set-Cookie"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 会话过期或已撤销；返回统一错误并清同名、相同ADMIN_COOKIE_PATH的cookie，不修改其他状态。 */
            401: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    /** @description iv_admin_session=; Max-Age=0；Path与显式ADMIN_COOKIE_PATH相同，保留HttpOnly/Secure/SameSite属性。 */
                    "Set-Cookie"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminOverview: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Overview"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListUsers: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                /** @description 受控字段方向枚举，追加实体主键ASC稳定排序、NULLS LAST；Membership主键user_id、Payment主键payment_intent映射id。 */
                sort?: "created_at:asc" | "created_at:desc" | "email:asc" | "email:desc";
                email?: string;
                enabled?: boolean;
                effective_vip?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminGetUser: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 不透明路径ID；不存在404。 */
                user_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetail"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminSetUserAccess: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
                /** @description 16..128 ASCII字符，各operation使用独立幂等空间，具体作用域见operation说明。账号启停保留actor_user_id+users.access+key作用域；会员控制使用users.membership独立回执，key唯一且指纹包含操作者、method、path、target及规范化body，跨操作者、目标或body复用会员key均409。指纹与审计结果action独立。默认保留结果30天至少7天，之后墓碑不可复用，不自动更换。 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description 不透明路径ID；不存在404。 */
                user_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccessPatch"];
            };
        };
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccessResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListJobs: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                /** @description 受控字段方向枚举，追加实体主键ASC稳定排序、NULLS LAST；Membership主键user_id、Payment主键payment_intent映射id。 */
                sort?: "created_at:asc" | "created_at:desc" | "updated_at:asc" | "updated_at:desc";
                user_id?: components["schemas"]["Id"];
                public_status?: "queued" | "downloading" | "merging" | "done" | "error";
                /** @description legacy_unset仅为查询伪值，匹配Job.internal_state IS NULL；response仍为null，不新增或写回业务状态。枚举与meta允许值取交集。 */
                internal_state?: "queued" | "running" | "retry_wait" | "succeeded" | "failed" | "needs_review" | "legacy_hold" | "legacy_unset";
                execution_version?: 1 | 2;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminGetJob: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 不透明路径ID；不存在404。 */
                job_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDetail"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListMemberships: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                /** @description 受控字段方向枚举，追加实体主键ASC稳定排序、NULLS LAST；Membership主键user_id、Payment主键payment_intent映射id。 */
                sort?: "expires_at:asc" | "expires_at:desc" | "user_id:asc";
                user_id?: components["schemas"]["Id"];
                effective?: boolean;
                status?: "free" | "active" | "expired";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListCheckouts: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                /** @description 受控字段方向枚举，追加实体主键ASC稳定排序、NULLS LAST；Membership主键user_id、Payment主键payment_intent映射id。 */
                sort?: "created_at:asc" | "created_at:desc";
                user_id?: components["schemas"]["Id"];
                /** @description 已知枚举与meta允许值交集；response仍为开放字符串，未来新增状态需契约修订后才能作为过滤值。 */
                state?: "pending" | "open" | "paid" | "expired" | "failed";
                reconciliation?: "not_started" | "unknown" | "verified" | "needs_review" | "closed";
                fulfilled?: boolean;
                provider_account_scope?: string;
                livemode?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckoutPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminGetCheckout: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 不透明路径ID；不存在404。 */
                checkout_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckoutDetail"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListPayments: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                /** @description 受控字段方向枚举，追加实体主键ASC稳定排序、NULLS LAST；Membership主键user_id、Payment主键payment_intent映射id。 */
                sort?: "id:asc" | "id:desc";
                user_id?: components["schemas"]["Id"];
                revoked?: boolean;
                payment_id?: components["schemas"]["Id"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminGetPayment: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 不透明路径ID；不存在404。 */
                payment_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentDetail"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListAuditLogs: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                /** @description 受控字段方向枚举，追加实体主键ASC稳定排序、NULLS LAST；Membership主键user_id、Payment主键payment_intent映射id。 */
                sort?: "recorded_at:asc" | "recorded_at:desc";
                actor_user_id?: components["schemas"]["Id"];
                target_user_id?: components["schemas"]["Id"];
                action?: string;
                outcome?: "succeeded" | "denied" | "failed";
                recorded_from?: string;
                recorded_before?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminSystemStatus: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemStatus"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminMeta: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 安全元数据。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminMeta"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminListSupportTickets: {
        parameters: {
            query?: {
                /** @description 页码，默认1。 */
                page?: components["parameters"]["Page"];
                /** @description 默认20、运行上限默认100，以meta为准；协议硬上限1000，超运行上限422。 */
                page_size?: components["parameters"]["PageSize"];
                sort?: "priority:desc" | "created_at:asc" | "created_at:desc";
                state?: "open" | "resolved" | "rejected";
                category?: "membership_not_credited" | "download_failing" | "login_problem" | "other";
                priority?: "priority" | "normal";
                user_id?: components["schemas"]["Id"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 工单分页；默认优先工单在前、再按提交时间升序。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportTicketPage"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminGetSupportTicket: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 工单ID；不存在404。 */
                ticket_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 工单详情：用户说明、勾选订单与会员投影、最近核实结果与可用操作及不可用原因。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportTicketDetail"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminReplySupportTicket: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
            };
            path: {
                /** @description 工单ID；不存在404。 */
                ticket_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SupportReply"];
            };
        };
        responses: {
            /** @description 以固定话术（可补一句）回复并结单。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportTicketState"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminRejectSupportTicket: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
            };
            path: {
                /** @description 工单ID；不存在404。 */
                ticket_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SupportReply"];
            };
        };
        responses: {
            /** @description 以固定话术驳回并结单。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportTicketState"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminVerifySupportPayment: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
            };
            path: {
                /** @description 工单ID；不存在404。 */
                ticket_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 以只读受限key向支付平台核实该订单付款并记录结果（不修改订单或会员）。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentCheck"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminReissueMembership: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
                /** @description 16..128 ASCII字符，各operation使用独立幂等空间，具体作用域见operation说明。账号启停保留actor_user_id+users.access+key作用域；会员控制使用users.membership独立回执，key唯一且指纹包含操作者、method、path、target及规范化body，跨操作者、目标或body复用会员key均409。指纹与审计结果action独立。默认保留结果30天至少7天，之后墓碑不可复用，不自动更换。 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description 工单ID；不存在404。 */
                ticket_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 补发成功：按订单天数延长会员、订单标记已履行、工单结单并自动回复。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReissueResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
    adminSetUserMembership: {
        parameters: {
            query?: never;
            header: {
                /** @description 已认证写操作必须带由独立ADMIN_CSRF_SECRET确定派生的会话CSRF token，同时验证ADMIN_ALLOWED_ORIGINS；Origin配置为空拒绝写，secret缺失或过短后台整体503 admin_unavailable。 */
                "X-CSRF-Token": components["parameters"]["Csrf"];
                /** @description 16..128 ASCII字符，各operation使用独立幂等空间，具体作用域见operation说明。账号启停保留actor_user_id+users.access+key作用域；会员控制使用users.membership独立回执，key唯一且指纹包含操作者、method、path、target及规范化body，跨操作者、目标或body复用会员key均409。指纹与审计结果action独立。默认保留结果30天至少7天，之后墓碑不可复用，不自动更换。 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description 不透明路径ID；不存在404。 */
                user_id: components["schemas"]["Id"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MembershipPatch"];
            };
        };
        responses: {
            /** @description 成功安全投影。 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["RequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationError"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["Unavailable"];
        };
    };
}

export type Schemas = components['schemas'];
