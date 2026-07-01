import type { ProjectStatus } from "@/lib/api";

const STATUS_STYLES: Record<ProjectStatus, string> = {
  created: "bg-gray-100 text-gray-700",
  uploaded: "bg-blue-100 text-blue-700",
  transcribing: "bg-yellow-100 text-yellow-800",
  transcribed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function StatusBadge({ status }: { status: ProjectStatus }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}
