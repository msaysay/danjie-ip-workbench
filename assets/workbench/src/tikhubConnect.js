/** Shared TikHub connect copy. The register link keeps the classroom referral. */
export const REGISTER_URL='https://user.tikhub.io/register?ref=u58I2I4n';
export const CONSOLE_URL='https://user.tikhub.io/dashboard/api';
export const DOCS_URL='https://docs.tikhub.io';
export const GUIDE_URL='https://tikhub.io/zh/getting-started';
export const SITE_URL='https://tikhub.io/';

export const WIZARD_STEPS=[
 {id:'connect',title:'连接'},
 {id:'register',title:'注册'},
 {id:'key',title:'配置 Key'},
 {id:'done',title:'完成连接'},
];

export const OUTSIDE_NOTE='工作台只是选题灵感的入口。配好的密钥也可以直接在 TikHub 官网或文档里用，能做的比这里更多。费用记在你的 TikHub 账户上，工作台不另收费，也不代充值。';
export const TRY_NOTE='更新一小批真实内容。次数算进今天的上限，失败不会自动重试。';

export function linksFrom(research){
 return {
  register:research?.register_url||REGISTER_URL,
  console:research?.console_url||CONSOLE_URL,
  docs:research?.docs_url||DOCS_URL,
  guide:research?.guide_url||GUIDE_URL,
  site:research?.site_url||SITE_URL,
 };
}
