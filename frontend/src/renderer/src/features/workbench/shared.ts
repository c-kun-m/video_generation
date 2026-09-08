export { unwrap } from "../../shared/request";
export const contentNames = {
  brief: "需求",
  script: "剧本",
  storyboard: "分镜",
};
export const reviewNames = {
  DRAFT: "待审批",
  APPROVED: "已批准",
  REJECTED: "已拒绝",
  REVOKED: "批准已撤销",
};
export const displayDate = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { hour12: false });
