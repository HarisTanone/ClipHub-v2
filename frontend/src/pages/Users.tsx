import { useState, useEffect } from "react";
import { UserPlus, Trash2, Edit3, Shield, X, Save } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { API_BASE, getToken } from "@/lib/api";
import { cn } from "@/lib/utils";

interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

async function fetchUsers(): Promise<User[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/auth/users`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return [];
  const data = await res.json();
  return data.data || data.users || [];
}

async function createUser(payload: { email: string; password: string; full_name: string; role?: string }): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/auth/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  return res.ok;
}

async function deleteUser(userId: number): Promise<boolean> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/auth/users/${userId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok;
}

export function Users() {
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  async function load() {
    setIsLoading(true);
    const data = await fetchUsers();
    setUsers(data);
    setIsLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function handleCreate() {
    if (!newEmail || !newPassword) { toast.error("Email and password required"); return; }
    setIsCreating(true);
    const ok = await createUser({ email: newEmail, password: newPassword, full_name: newName });
    if (ok) {
      toast.success("User created");
      setShowCreate(false);
      setNewEmail(""); setNewName(""); setNewPassword("");
      load();
    } else {
      toast.error("Failed to create user");
    }
    setIsCreating(false);
  }

  async function handleDelete(userId: number, email: string) {
    if (!confirm(`Deactivate user ${email}?`)) return;
    const ok = await deleteUser(userId);
    if (ok) { toast.success("User deactivated"); load(); }
    else { toast.error("Failed to delete user"); }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between shrink-0 mb-4">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">User Management</h1>
          <p className="text-[11px] text-zinc-500">{users.length} users</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)} icon={showCreate ? <X className="h-3.5 w-3.5" /> : <UserPlus className="h-3.5 w-3.5" />}>
          {showCreate ? "Cancel" : "Add User"}
        </Button>
      </div>

      {/* Create form */}
      {showCreate && (
        <Card className="p-4 mb-4 shrink-0">
          <h3 className="text-xs font-semibold text-zinc-300 mb-3">New User</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Input label="Email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="user@email.com" />
            <Input label="Full Name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="John Doe" />
            <Input label="Password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="min 6 chars" />
          </div>
          <Button size="sm" className="mt-3" onClick={handleCreate} loading={isCreating} icon={<Save className="h-3 w-3" />}>Create User</Button>
        </Card>
      )}

      {/* User list */}
      <Card className="flex-1 p-0 min-h-0 flex flex-col">
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 text-sm text-zinc-500">Loading...</div>
          ) : users.length === 0 ? (
            <div className="p-8 text-center text-sm text-zinc-500">No users found</div>
          ) : (
            <div className="divide-y divide-zinc-800/30">
              {users.map((user) => (
                <div key={user.id} className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/10">
                  {/* Avatar */}
                  <div className="shrink-0 w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center">
                    <span className="text-[11px] font-bold text-zinc-400">{user.full_name?.[0] || user.email[0].toUpperCase()}</span>
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm text-zinc-200 font-medium truncate">{user.full_name || user.email}</p>
                      <Badge variant={user.role === "superadmin" ? "success" : "default"} size="sm">
                        {user.role}
                      </Badge>
                      {!user.is_active && <Badge variant="error" size="sm">Inactive</Badge>}
                    </div>
                    <p className="text-[10px] text-zinc-500">{user.email}</p>
                  </div>
                  {/* Actions */}
                  <div className="shrink-0 flex items-center gap-1">
                    {user.role !== "superadmin" && (
                      <button
                        type="button"
                        onClick={() => handleDelete(user.id, user.email)}
                        className="p-1.5 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                        title="Deactivate"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
