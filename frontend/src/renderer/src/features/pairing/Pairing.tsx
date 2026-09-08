import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ErrorBox, Icon } from "../../components/ui";
import { unwrap } from "../../shared/request";
import s from "../../App.module.css";

export function Pairing() {
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      unwrap(
        window.video.pair({
          pairing_code: code.trim(),
          device_name: "我的桌面",
        }),
      ),
    onSuccess: () => {
      setCode("");
      void qc.invalidateQueries();
    },
  });
  return (
    <div className={s.pairLayout}>
      <div>
        <span className={s.eyebrow}>YOUR NEXT STORY STARTS HERE</span>
        <h1 className={s.pairTitle}>
          让想法，
          <br />
          成为下一支短片。
        </h1>
        <p className={s.lead}>
          连接本机创作服务，
          <br />
          为你的故事建立一个专属项目。
        </p>
        <div className={s.pairArt}>
          <div />
          <div />
          <div />
          <span>IDEA → STORY → VIDEO</span>
        </div>
      </div>
      <section className={s.pairCard}>
        <span className={s.stepNumber}>01 / CONNECT</span>
        <h2>配对你的设备</h2>
        <p>在项目目录运行下方命令，获取一次性配对码。</p>
        <code>.\scripts\dev.ps1 pair</code>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <label htmlFor="pair-code">一次性配对码</label>
          <input
            id="pair-code"
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
            placeholder="粘贴配对码"
            required
            minLength={16}
            maxLength={256}
          />
          <ErrorBox error={mutation.error} />
          <button className={s.primary} disabled={mutation.isPending}>
            {mutation.isPending ? "正在配对…" : "连接工作空间"}
            <Icon name="arrow" />
          </button>
        </form>
        <small>配对码 10 分钟内有效 · 凭据由系统加密保存</small>
      </section>
    </div>
  );
}
