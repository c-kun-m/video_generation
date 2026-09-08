import type { Schema } from "../../../../shared/bridge";
import s from "./Workbench.module.css";

type Payload = Schema["SaveRevision"]["payload"];
type Head = Schema["ContentHead"];
export function emptyContent(kind: Payload["kind"]): Payload {
  if (kind === "brief")
    return {
      kind,
      theme: "",
      audience: "",
      purpose: "",
      style: "",
      constraints: "",
    };
  if (kind === "script") return { kind, brief_ref: null, segments: [] };
  return { kind, script_ref: null, fps: 24, shots: [] };
}

export function exampleContent(kind: Payload["kind"], heads: Head[]): Payload {
  if (kind === "brief")
    return {
      kind,
      theme: "城市清晨的三种声音",
      audience: "喜欢生活记录的年轻人",
      purpose: "用三个镜头展示城市苏醒",
      style: "温暖、写实、轻快",
      constraints: "中文旁白，竖屏，30 秒",
    };
  const brief = heads.find((h) => h.entity_kind === "brief");
  const script = heads.find((h) => h.entity_kind === "script");
  if (kind === "script")
    return {
      kind,
      brief_ref: brief?.current.ref ?? null,
      segments: [
        {
          segment_id: crypto.randomUUID(),
          spoken_text: "天色渐亮，第一班列车驶过桥面，城市开始了新的一天。",
          visual_description: "晨光中的列车",
        },
        {
          segment_id: crypto.randomUUID(),
          spoken_text: "街角的店铺升起热气，熟悉的招呼声，把街道慢慢唤醒。",
          visual_description: "早餐摊与行人",
        },
        {
          segment_id: crypto.randomUUID(),
          spoken_text: "跟着阳光出发，每个平凡的早晨，都藏着新的期待。",
          visual_description: "阳光下的人群",
        },
      ],
    };
  const segments =
    script?.current.payload.kind === "script"
      ? (script.current.payload.segments ?? [])
      : [];
  return {
    kind,
    script_ref: script?.current.ref ?? null,
    fps: 24,
    shots: [0, 1, 2].map((i) => ({
      shot_id: crypto.randomUUID(),
      segment_ids: segments[i] ? [segments[i].segment_id] : [],
      intent: ["建立清晨城市的环境", "展示街角的生活细节", "用人群出发收尾"][i],
      camera: ["远景缓慢横移", "中景缓慢推进", "跟随镜头"][i],
      duration_frames: 240,
    })),
  };
}

function TextField({
  label,
  value,
  change,
}: {
  label: string;
  value: string;
  change: (value: string) => void;
}) {
  return (
    <label className={s.field}>
      <span>{label}</span>
      <textarea
        aria-label={label}
        value={value}
        rows={3}
        maxLength={20000}
        onChange={(event) => change(event.target.value)}
      />
    </label>
  );
}

export function ContentFields({
  payload,
  heads,
  onChange,
  disabled,
}: {
  payload: Payload;
  heads: Head[];
  onChange: (payload: Payload) => void;
  disabled: boolean;
}) {
  const upstreamKind = payload.kind === "script" ? "brief" : "script";
  const upstream = heads.find((h) => h.entity_kind === upstreamKind);
  const reference =
    payload.kind === "script"
      ? payload.brief_ref
      : payload.kind === "storyboard"
        ? payload.script_ref
        : null;
  return (
    <fieldset disabled={disabled} className={s.fields}>
      {payload.kind !== "brief" && (
        <div className={s.reference}>
          <span>
            {upstreamKind === "brief" ? "需求" : "剧本"}来源：
            {reference
              ? `已关联${reference.revision_id === upstream?.current.ref.revision_id ? "当前版本" : "历史版本"}`
              : "尚未关联"}
          </span>
          <button
            type="button"
            className={s.secondary}
            disabled={!upstream}
            onClick={() => {
              if (!upstream) return;
              onChange(
                payload.kind === "script"
                  ? { ...payload, brief_ref: upstream.current.ref }
                  : { ...payload, script_ref: upstream.current.ref },
              );
            }}
          >
            关联当前{upstreamKind === "brief" ? "需求" : "剧本"}
            {upstream ? ` v${upstream.current.revision}` : ""}
          </button>
        </div>
      )}
      {payload.kind === "brief" && (
        <div className={s.formGrid}>
          {(
            [
              ["theme", "主题"],
              ["audience", "目标受众"],
              ["purpose", "视频目的"],
              ["style", "表达风格"],
              ["constraints", "其他要求（选填）"],
            ] as const
          ).map(([key, label]) => (
            <TextField
              key={key}
              label={label}
              value={payload[key] ?? ""}
              change={(value) => onChange({ ...payload, [key]: value })}
            />
          ))}
        </div>
      )}
      {payload.kind === "script" && (
        <>
          {(payload.segments ?? []).map((segment, index) => (
            <section className={s.card} key={segment.segment_id}>
              <div className={s.row}>
                <h3>段落 {index + 1}</h3>
                <div className={s.actions}>
                  <button
                    className={s.secondary}
                    type="button"
                    disabled={index === 0}
                    onClick={() => {
                      const segments = [...payload.segments!];
                      [segments[index - 1], segments[index]] = [
                        segments[index],
                        segments[index - 1],
                      ];
                      onChange({ ...payload, segments });
                    }}
                  >
                    上移
                  </button>
                  <button
                    className={s.secondary}
                    type="button"
                    onClick={() =>
                      onChange({
                        ...payload,
                        segments: payload.segments!.filter(
                          (s) => s.segment_id !== segment.segment_id,
                        ),
                      })
                    }
                  >
                    移除段落
                  </button>
                </div>
              </div>
              <TextField
                label={`段落 ${index + 1} 旁白`}
                value={segment.spoken_text ?? ""}
                change={(value) =>
                  onChange({
                    ...payload,
                    segments: payload.segments!.map((s) =>
                      s.segment_id === segment.segment_id
                        ? { ...s, spoken_text: value }
                        : s,
                    ),
                  })
                }
              />
              <TextField
                label={`段落 ${index + 1} 画面描述`}
                value={segment.visual_description ?? ""}
                change={(value) =>
                  onChange({
                    ...payload,
                    segments: payload.segments!.map((s) =>
                      s.segment_id === segment.segment_id
                        ? { ...s, visual_description: value }
                        : s,
                    ),
                  })
                }
              />
            </section>
          ))}
          <button
            type="button"
            className={s.secondary}
            onClick={() =>
              onChange({
                ...payload,
                segments: [
                  ...(payload.segments ?? []),
                  {
                    segment_id: crypto.randomUUID(),
                    spoken_text: "",
                    visual_description: "",
                  },
                ],
              })
            }
          >
            ＋ 添加段落
          </button>
        </>
      )}
      {payload.kind === "storyboard" && (
        <>
          <p className={s.hint}>
            3–8 个镜头，总计划时长 30–60 秒。当前{" "}
            {(
              (payload.shots ?? []).reduce(
                (sum, s) => sum + (s.duration_frames ?? 240),
                0,
              ) / 24
            ).toFixed(1)}{" "}
            秒；此处为人工计划时长。
          </p>
          {(payload.shots ?? []).map((shot, index) => (
            <section className={s.card} key={shot.shot_id}>
              <div className={s.row}>
                <h3>镜头 {String(index + 1).padStart(2, "0")}</h3>
                <div className={s.actions}>
                  <button
                    className={s.secondary}
                    type="button"
                    disabled={index === 0}
                    onClick={() => {
                      const shots = [...payload.shots!];
                      [shots[index - 1], shots[index]] = [
                        shots[index],
                        shots[index - 1],
                      ];
                      onChange({ ...payload, shots });
                    }}
                  >
                    上移
                  </button>
                  <button
                    type="button"
                    className={s.secondary}
                    onClick={() =>
                      onChange({
                        ...payload,
                        shots: payload.shots!.filter(
                          (s) => s.shot_id !== shot.shot_id,
                        ),
                      })
                    }
                  >
                    移除镜头
                  </button>
                </div>
              </div>
              <TextField
                label={`镜头 ${index + 1} 画面意图`}
                value={shot.intent ?? ""}
                change={(value) =>
                  onChange({
                    ...payload,
                    shots: payload.shots!.map((s) =>
                      s.shot_id === shot.shot_id ? { ...s, intent: value } : s,
                    ),
                  })
                }
              />
              <div className={s.formGrid}>
                <TextField
                  label={`镜头 ${index + 1} 运镜`}
                  value={shot.camera ?? ""}
                  change={(value) =>
                    onChange({
                      ...payload,
                      shots: payload.shots!.map((s) =>
                        s.shot_id === shot.shot_id
                          ? { ...s, camera: value }
                          : s,
                      ),
                    })
                  }
                />
                <label className={s.field}>
                  <span>计划时长（秒）</span>
                  <input
                    type="number"
                    min={1 / 24}
                    max={60}
                    step={1 / 24}
                    value={(shot.duration_frames ?? 240) / 24}
                    onChange={(event) => {
                      const seconds = Number(event.target.value);
                      if (
                        Number.isFinite(seconds) &&
                        seconds > 0 &&
                        seconds <= 60
                      )
                        onChange({
                          ...payload,
                          shots: payload.shots!.map((s) =>
                            s.shot_id === shot.shot_id
                              ? {
                                  ...s,
                                  duration_frames: Math.round(seconds * 24),
                                }
                              : s,
                          ),
                        });
                    }}
                  />
                </label>
              </div>
              <div className={s.field}>
                <span>关联旁白段落</span>
                <div className={s.checks}>
                  {upstream?.current.payload.kind === "script" &&
                    (upstream.current.payload.segments ?? []).map(
                      (segment, i) => (
                        <label key={segment.segment_id}>
                          <input
                            type="checkbox"
                            checked={(shot.segment_ids ?? []).includes(
                              segment.segment_id,
                            )}
                            onChange={(event) =>
                              onChange({
                                ...payload,
                                shots: payload.shots!.map((s) =>
                                  s.shot_id === shot.shot_id
                                    ? {
                                        ...s,
                                        segment_ids: event.target.checked
                                          ? [
                                              ...(s.segment_ids ?? []),
                                              segment.segment_id,
                                            ]
                                          : (s.segment_ids ?? []).filter(
                                              (id) => id !== segment.segment_id,
                                            ),
                                      }
                                    : s,
                                ),
                              })
                            }
                          />
                          段落 {i + 1}：{segment.spoken_text?.slice(0, 28)}
                        </label>
                      ),
                    )}
                </div>
              </div>
            </section>
          ))}
          <button
            type="button"
            className={s.secondary}
            disabled={(payload.shots?.length ?? 0) >= 8}
            onClick={() =>
              onChange({
                ...payload,
                shots: [
                  ...(payload.shots ?? []),
                  {
                    shot_id: crypto.randomUUID(),
                    segment_ids: [],
                    intent: "",
                    camera: "",
                    duration_frames: 240,
                  },
                ],
              })
            }
          >
            ＋ 添加镜头
          </button>
        </>
      )}
    </fieldset>
  );
}
