"use client";

import { useRef, useCallback } from "react";
import { Play, AlignLeft } from "lucide-react";
import dynamic from "next/dynamic";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center rounded-lg border border-border-default bg-navy-900">
      <span className="text-sm text-text-muted">Loading editor...</span>
    </div>
  ),
});

interface QueryEditorProps {
  value: string;
  onChange: (value: string) => void;
  onRun: () => void;
  language?: string;
  placeholder?: string;
  height?: string;
}

export function QueryEditor({
  value,
  onChange,
  onRun,
  language = "sql",
  placeholder = "Enter your query...",
  height = "120px",
}: QueryEditorProps) {
  const editorRef = useRef<unknown>(null);

  const handleEditorMount = useCallback(
    (editor: unknown) => {
      editorRef.current = editor;
      const monacoEditor = editor as {
        addCommand: (keybinding: number, handler: () => void) => void;
      };
      // Register Ctrl+Enter to run
      monacoEditor.addCommand(
        2048 | 3, // KeyMod.CtrlCmd | KeyCode.Enter
        () => onRun(),
      );
    },
    [onRun],
  );

  const handleFormat = () => {
    if (editorRef.current) {
      const editor = editorRef.current as {
        getAction: (id: string) => { run: () => void } | null;
      };
      editor.getAction("editor.action.formatDocument")?.run();
    }
  };

  return (
    <div className="overflow-hidden rounded-lg border border-border-default bg-navy-900">
      <div className="flex items-center justify-between border-b border-border-default px-3 py-1.5">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Query
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleFormat}
            className="rounded p-1 text-text-muted transition-colors hover:bg-navy-700 hover:text-text-primary"
            title="Format"
          >
            <AlignLeft className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onRun}
            className="flex items-center gap-1.5 rounded bg-cyan-500/15 px-2.5 py-1 text-xs font-medium text-cyan-400 transition-colors hover:bg-cyan-500/25"
            title="Run (Ctrl+Enter)"
          >
            <Play className="h-3 w-3" />
            Run
          </button>
        </div>
      </div>
      <MonacoEditor
        height={height}
        language={language}
        theme="vs-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        onMount={handleEditorMount}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: "off",
          scrollBeyondLastLine: false,
          wordWrap: "on",
          padding: { top: 8, bottom: 8 },
          renderLineHighlight: "none",
          overviewRulerLanes: 0,
          hideCursorInOverviewRuler: true,
          scrollbar: { vertical: "hidden", horizontal: "auto" },
          placeholder,
        }}
      />
    </div>
  );
}
