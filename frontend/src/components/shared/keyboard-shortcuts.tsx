"use client";

import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X, Keyboard } from "lucide-react";

interface ShortcutGroup {
  title: string;
  shortcuts: { keys: string[]; description: string }[];
}

const shortcutGroups: ShortcutGroup[] = [
  {
    title: "Navigation",
    shortcuts: [
      { keys: ["G", "D"], description: "Go to Dashboard" },
      { keys: ["G", "L"], description: "Go to Logs" },
      { keys: ["G", "M"], description: "Go to Metrics" },
      { keys: ["G", "T"], description: "Go to Traces" },
      { keys: ["G", "A"], description: "Go to Agents" },
    ],
  },
  {
    title: "Global",
    shortcuts: [
      { keys: ["\u2318", "K"], description: "Open command palette" },
      { keys: ["?"], description: "Show keyboard shortcuts" },
      { keys: ["Esc"], description: "Close dialog / panel" },
    ],
  },
  {
    title: "Log Explorer",
    shortcuts: [
      { keys: ["/"], description: "Focus search" },
      { keys: ["J"], description: "Next log entry" },
      { keys: ["K"], description: "Previous log entry" },
    ],
  },
];

export function KeyboardShortcuts() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let waitingForSecond = false;

    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      if (isInput) return;
      if (waitingForSecond) return;

      if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border-default bg-surface-primary shadow-2xl shadow-black/40 outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border-default px-5 py-4">
            <div className="flex items-center gap-2.5">
              <Keyboard className="h-4 w-4 text-cyan-400" />
              <Dialog.Title className="text-sm font-semibold text-text-primary">
                Keyboard Shortcuts
              </Dialog.Title>
            </div>
            <Dialog.Close className="rounded-md p-1 text-text-muted hover:bg-navy-700 hover:text-text-primary transition-colors">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Shortcuts grid */}
          <div className="max-h-[400px] overflow-y-auto p-5 space-y-5">
            {shortcutGroups.map((group) => (
              <div key={group.title}>
                <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-widest text-text-muted">
                  {group.title}
                </h3>
                <div className="space-y-1.5">
                  {group.shortcuts.map((shortcut) => (
                    <div
                      key={shortcut.description}
                      className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-navy-800 transition-colors"
                    >
                      <span className="text-sm text-text-secondary">
                        {shortcut.description}
                      </span>
                      <div className="flex items-center gap-1">
                        {shortcut.keys.map((key, i) => (
                          <span key={i}>
                            {i > 0 && (
                              <span className="mx-0.5 text-[10px] text-text-muted">
                                then
                              </span>
                            )}
                            <kbd className="inline-flex min-w-[22px] items-center justify-center rounded border border-border-default bg-navy-800 px-1.5 py-0.5 text-[11px] font-medium text-text-secondary">
                              {key}
                            </kbd>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
