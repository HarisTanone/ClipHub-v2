import { RbacManager } from "@/components/settings/RbacManager";

export function Users() {
  return (
    <div className="flex h-full min-h-0 flex-col space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Access Control &amp; RBAC</h1>
        <p className="text-[11px] text-zinc-400">
          Manajemen pengguna, penugasan role, status akun, dan matriks hak akses permission sistem.
        </p>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <RbacManager />
      </div>
    </div>
  );
}
