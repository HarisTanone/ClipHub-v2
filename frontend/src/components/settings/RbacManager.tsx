import { useState, useEffect, useMemo } from "react";
import {
  Shield, Users, UserPlus, Key, Check, X, Lock, Edit3, Trash2,
  Plus, Search, RefreshCw, AlertCircle, ShieldAlert, Sparkles,
  CheckSquare, Square, Layers, UserCheck, ChevronRight, Filter
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { confirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/hooks/useAuth";
import {
  rbacApi,
  type RoleItem,
  type PermissionItem,
  type UserListItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export function RbacManager() {
  const toast = useToast();
  const { user: currentUser, isSuperadmin, can } = useAuth();

  const [activeSubTab, setActiveSubTab] = useState<"users" | "roles">("users");

  // Data states
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [permissionsGrouped, setPermissionsGrouped] = useState<Record<string, PermissionItem[]>>({});
  const [isLoading, setIsLoading] = useState(true);

  // Filter states
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");

  // User Modals
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserListItem | null>(null);

  // User Form states
  const [formEmail, setFormEmail] = useState("");
  const [formName, setFormName] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formRoleId, setFormRoleId] = useState<number>(3); // default editor
  const [formIsPremium, setFormIsPremium] = useState(false);
  const [formIsActive, setFormIsActive] = useState(true);
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);

  // Role Modals
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null);
  const [roleName, setRoleName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [selectedPermissionIds, setSelectedPermissionIds] = useState<number[]>([]);
  const [isSubmittingRole, setIsSubmittingRole] = useState(false);

  // Role detail view in matrix
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);

  async function loadData() {
    setIsLoading(true);
    try {
      const [usersData, rolesData, permsData] = await Promise.all([
        rbacApi.getUsers(),
        rbacApi.getRoles(),
        rbacApi.getPermissions(),
      ]);
      setUsers(usersData);
      setRoles(rolesData);
      setPermissionsGrouped(permsData);
      if (rolesData.length > 0 && selectedRoleId === null) {
        setSelectedRoleId(rolesData[0].id);
      }
    } catch (err: any) {
      toast.error(err.message || "Gagal memuat data akses dan pengguna");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  // Filtered users
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      const matchesSearch =
        u.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        u.full_name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesRole = roleFilter === "all" || u.role === roleFilter;
      return matchesSearch && matchesRole;
    });
  }, [users, searchQuery, roleFilter]);

  // Selected role for matrix view
  const activeRole = useMemo(() => {
    return roles.find((r) => r.id === selectedRoleId) || roles[0] || null;
  }, [roles, selectedRoleId]);

  // User Actions
  function openAddUser() {
    setFormEmail("");
    setFormName("");
    setFormPassword("");
    setFormRoleId(roles.find((r) => r.name === "editor")?.id || (roles[0]?.id ?? 3));
    setFormIsPremium(false);
    setFormIsActive(true);
    setShowAddUserModal(true);
  }

  function openEditUser(user: UserListItem) {
    setEditingUser(user);
    setFormEmail(user.email);
    setFormName(user.full_name);
    setFormPassword("");
    setFormRoleId(user.role_id || (roles[0]?.id ?? 3));
    setFormIsPremium(user.is_premium);
    setFormIsActive(user.is_active);
  }

  async function handleCreateUser() {
    if (!formEmail.trim() || !formPassword.trim()) {
      toast.error("Email dan kata sandi wajib diisi");
      return;
    }
    setIsSubmittingUser(true);
    try {
      await rbacApi.createUser({
        email: formEmail.trim(),
        password: formPassword,
        full_name: formName.trim() || formEmail.trim().split("@")[0],
        role_id: formRoleId,
        is_premium: formIsPremium,
      });
      toast.success(`Pengguna ${formEmail} berhasil dibuat`);
      setShowAddUserModal(false);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal membuat pengguna");
    } finally {
      setIsSubmittingUser(false);
    }
  }

  async function handleUpdateUser() {
    if (!editingUser) return;
    setIsSubmittingUser(true);
    try {
      await rbacApi.updateUser(editingUser.id, {
        full_name: formName.trim(),
        role_id: formRoleId,
        is_active: formIsActive,
        is_premium: formIsPremium,
        ...(formPassword.trim() ? { password: formPassword } : {}),
      });
      toast.success(`Pengguna ${editingUser.email} berhasil diperbarui`);
      setEditingUser(null);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal memperbarui pengguna");
    } finally {
      setIsSubmittingUser(false);
    }
  }

  async function handleToggleUserStatus(user: UserListItem) {
    if (user.id === currentUser?.id) {
      toast.error("Tidak dapat menonaktifkan akun sendiri");
      return;
    }
    try {
      await rbacApi.updateUser(user.id, { is_active: !user.is_active });
      toast.success(`${user.email} ${!user.is_active ? "diaktifkan" : "dinonaktifkan"}`);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal mengubah status pengguna");
    }
  }

  async function handleToggleUserPremium(user: UserListItem) {
    try {
      await rbacApi.setPremium(user.id, !user.is_premium);
      toast.success(`${user.email} -> ${!user.is_premium ? "Premium (V1 Gemini)" : "Free (V2 9router)"}`);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal mengubah status premium");
    }
  }

  async function handleDeleteUser(user: UserListItem) {
    if (user.id === currentUser?.id) {
      toast.error("Tidak dapat menghapus akun sendiri");
      return;
    }
    const ok = await confirmDialog({
      title: "Deaktivasi Pengguna?",
      message: `Akun ${user.email} akan dinonaktifkan dan sesi login akan dicabut.`,
      confirmText: "Deaktivasi",
      danger: true,
    });
    if (!ok) return;

    try {
      await rbacApi.deleteUser(user.id);
      toast.success(`Pengguna ${user.email} dinonaktifkan`);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal mendeaktivasi pengguna");
    }
  }

  // Role Actions
  function openCreateRole() {
    setEditingRole(null);
    setRoleName("");
    setRoleDescription("");
    setSelectedPermissionIds([]);
    setShowRoleModal(true);
  }

  function openEditRole(role: RoleItem) {
    setEditingRole(role);
    setRoleName(role.name);
    setRoleDescription(role.description || "");
    setSelectedPermissionIds(role.permissions.map((p) => p.id));
    setShowRoleModal(true);
  }

  async function handleSaveRole() {
    if (!roleName.trim()) {
      toast.error("Nama role wajib diisi");
      return;
    }
    setIsSubmittingRole(true);
    try {
      if (editingRole) {
        await rbacApi.updateRole(editingRole.id, {
          name: editingRole.is_system ? undefined : roleName.trim(),
          description: roleDescription.trim(),
          permission_ids: selectedPermissionIds,
        });
        toast.success(`Role '${editingRole.name}' berhasil diperbarui`);
      } else {
        await rbacApi.createRole({
          name: roleName.trim(),
          description: roleDescription.trim(),
          permission_ids: selectedPermissionIds,
        });
        toast.success(`Role '${roleName.trim()}' berhasil dibuat`);
      }
      setShowRoleModal(false);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal menyimpan role");
    } finally {
      setIsSubmittingRole(false);
    }
  }

  async function handleDeleteRole(role: RoleItem) {
    if (role.is_system) {
      toast.error(`Role sistem '${role.name}' dilindungi dan tidak dapat dihapus`);
      return;
    }
    const ok = await confirmDialog({
      title: "Hapus Role Kustom?",
      message: `Role '${role.name}' akan dihapus dan pengguna yang terkait akan dialihkan ke role default.`,
      confirmText: "Hapus",
      danger: true,
    });
    if (!ok) return;

    try {
      await rbacApi.deleteRole(role.id);
      toast.success(`Role '${role.name}' berhasil dihapus`);
      loadData();
    } catch (err: any) {
      toast.error(err.message || "Gagal menghapus role");
    }
  }

  function togglePermission(permId: number) {
    setSelectedPermissionIds((prev) =>
      prev.includes(permId) ? prev.filter((id) => id !== permId) : [...prev, permId]
    );
  }

  function toggleCategoryPermissions(categoryPerms: PermissionItem[]) {
    const catIds = categoryPerms.map((p) => p.id);
    const allSelected = catIds.every((id) => selectedPermissionIds.includes(id));
    if (allSelected) {
      setSelectedPermissionIds((prev) => prev.filter((id) => !catIds.includes(id)));
    } else {
      setSelectedPermissionIds((prev) => Array.from(new Set([...prev, ...catIds])));
    }
  }

  // Category labels helper
  const categoryLabels: Record<string, string> = {
    jobs: "Video Jobs & Pipeline",
    styles: "Styles, Presets & B-Roll",
    autopilot: "Hermes Autopilot",
    video_gen: "AI Video Generator",
    social: "Social Channels & Telegram",
    settings: "System & AI Settings",
    rbac: "Users & Access Control",
    system: "System Operations",
    general: "General",
  };

  return (
    <div className="space-y-4">
      {/* Sub-tab Switcher Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-2.5 backdrop-blur-sm">
        <div className="flex items-center gap-1.5 bg-zinc-950/80 border border-zinc-800/80 p-1 rounded-xl">
          <button
            type="button"
            onClick={() => setActiveSubTab("users")}
            className={cn(
              "flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all",
              activeSubTab === "users"
                ? "bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700/80"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
            )}
          >
            <Users className="h-3.5 w-3.5 text-violet-400" />
            <span>Pengguna ({users.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab("roles")}
            className={cn(
              "flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all",
              activeSubTab === "roles"
                ? "bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700/80"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
            )}
          >
            <Shield className="h-3.5 w-3.5 text-indigo-400" />
            <span>Roles &amp; Permission Matrix ({roles.length})</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={loadData}
            loading={isLoading}
            icon={<RefreshCw className="h-3.5 w-3.5" />}
          >
            Refresh
          </Button>
          {activeSubTab === "users" ? (
            <Button
              size="sm"
              onClick={openAddUser}
              icon={<UserPlus className="h-3.5 w-3.5" />}
            >
              Tambah Pengguna
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={openCreateRole}
              icon={<Plus className="h-3.5 w-3.5" />}
            >
              Buat Role Baru
            </Button>
          )}
        </div>
      </div>

      {/* ─── TAB 1: USERS ──────────────────────────────────────────────────────── */}
      {activeSubTab === "users" && (
        <div className="space-y-4">
          {/* Filter Bar */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
              <input
                type="text"
                placeholder="Cari berdasarkan nama atau email..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-zinc-950/60 border border-zinc-800 rounded-xl pl-9 pr-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-violet-500/50 transition-colors"
              />
            </div>
            <div className="w-full sm:w-48">
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="w-full bg-zinc-950/60 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-violet-500/50 transition-colors"
              >
                <option value="all">Semua Role</option>
                {roles.map((r) => (
                  <option key={r.id} value={r.name}>
                    Role: {r.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Users Table */}
          <Card className="p-0 overflow-hidden border-zinc-800/80 bg-zinc-950/60">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-zinc-900/60 border-b border-zinc-800 text-zinc-400">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Pengguna</th>
                    <th className="px-4 py-3 font-semibold">Role</th>
                    <th className="px-4 py-3 font-semibold">Plan Pipeline</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Login Terakhir</th>
                    <th className="px-4 py-3 font-semibold text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {isLoading ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                        Memuat data pengguna...
                      </td>
                    </tr>
                  ) : filteredUsers.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                        Tidak ada pengguna yang cocok dengan kriteria pencarian.
                      </td>
                    </tr>
                  ) : (
                    filteredUsers.map((u) => {
                      const isSelf = u.id === currentUser?.id;
                      const isSuper = u.role === "superadmin";
                      return (
                        <tr key={u.id} className="hover:bg-zinc-900/40 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-zinc-800 to-zinc-900 border border-zinc-700 flex items-center justify-center text-xs font-bold text-zinc-300">
                                {(u.full_name || u.email)[0].toUpperCase()}
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5">
                                  <p className="font-medium text-zinc-200 truncate">{u.full_name || "Tanpa Nama"}</p>
                                  {isSelf && (
                                    <span className="text-[9px] font-medium px-1 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20">
                                      Akun Anda
                                    </span>
                                  )}
                                </div>
                                <p className="text-[11px] text-zinc-500 truncate">{u.email}</p>
                              </div>
                            </div>
                          </td>

                          <td className="px-4 py-3">
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium border",
                                isSuper
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                  : u.role === "admin"
                                  ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                                  : u.role === "editor"
                                  ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/30"
                                  : "bg-zinc-800 text-zinc-400 border-zinc-700"
                              )}
                            >
                              <Shield className="h-3 w-3" />
                              {u.role}
                            </span>
                          </td>

                          <td className="px-4 py-3">
                            <button
                              type="button"
                              onClick={() => handleToggleUserPremium(u)}
                              className={cn(
                                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition-colors",
                                u.is_premium
                                  ? "border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
                                  : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                              )}
                            >
                              <span className={cn("h-2 w-2 rounded-full", u.is_premium ? "bg-amber-400" : "bg-zinc-600")} />
                              {u.is_premium ? "Premium (V1 Gemini)" : "Free (V2 9router)"}
                            </button>
                          </td>

                          <td className="px-4 py-3">
                            <button
                              type="button"
                              onClick={() => handleToggleUserStatus(u)}
                              disabled={isSelf}
                              className={cn(
                                "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border transition-colors",
                                u.is_active
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20"
                                  : "bg-red-500/10 text-red-400 border-red-500/20 hover:bg-red-500/20"
                              )}
                            >
                              {u.is_active ? "Aktif" : "Nonaktif"}
                            </button>
                          </td>

                          <td className="px-4 py-3 text-zinc-500 text-[11px]">
                            {u.last_login_at ? new Date(u.last_login_at).toLocaleString("id-ID") : "Belum pernah"}
                          </td>

                          <td className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                type="button"
                                onClick={() => openEditUser(u)}
                                className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
                                title="Edit Pengguna"
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </button>
                              {!isSelf && (
                                <button
                                  type="button"
                                  onClick={() => handleDeleteUser(u)}
                                  className="p-1.5 rounded-lg text-zinc-400 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                                  title="Deaktivasi Akun"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ─── TAB 2: ROLES & PERMISSIONS MATRIX ─────────────────────────────────── */}
      {activeSubTab === "roles" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left Column: Role Cards */}
          <div className="lg:col-span-4 space-y-3">
            <div className="flex items-center justify-between px-1">
              <span className="text-xs font-semibold text-zinc-300">Daftar Role ({roles.length})</span>
              <Button size="sm" variant="outline" onClick={openCreateRole} icon={<Plus className="h-3.5 w-3.5" />}>
                Role Baru
              </Button>
            </div>

            <div className="space-y-2">
              {roles.map((r) => {
                const isSelected = selectedRoleId === r.id;
                return (
                  <div
                    key={r.id}
                    onClick={() => setSelectedRoleId(r.id)}
                    className={cn(
                      "group p-3 rounded-xl border text-left cursor-pointer transition-all",
                      isSelected
                        ? "bg-zinc-900 border-violet-500/50 shadow-md ring-1 ring-violet-500/20"
                        : "bg-zinc-950/60 border-zinc-800/80 hover:bg-zinc-900/60 hover:border-zinc-700"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <div
                          className={cn(
                            "h-7 w-7 rounded-lg flex items-center justify-center border",
                            r.name === "superadmin"
                              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                              : r.is_system
                              ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-400"
                              : "bg-violet-500/10 border-violet-500/30 text-violet-400"
                          )}
                        >
                          <Shield className="h-3.5 w-3.5" />
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-semibold text-zinc-100">{r.name}</span>
                            {r.is_system ? (
                              <span className="text-[9px] px-1 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                                Sistem
                              </span>
                            ) : (
                              <span className="text-[9px] px-1 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20">
                                Kustom
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-zinc-400 line-clamp-1">{r.description || "Tidak ada deskripsi"}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openEditRole(r);
                          }}
                          className="p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                          title="Edit Role & Permissions"
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </button>
                        {!r.is_system && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteRole(r);
                            }}
                            className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                            title="Hapus Role"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="mt-2.5 pt-2 border-t border-zinc-800/60 flex items-center justify-between text-[10px] text-zinc-500">
                      <span>{r.user_count || 0} Pengguna Aktif</span>
                      <span>{r.name === "superadmin" ? "Semua Akses (*)" : `${r.permissions.length} Hak Akses`}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Permission Matrix for Active Role */}
          <div className="lg:col-span-8 space-y-3">
            {activeRole ? (
              <Card className="p-4 border-zinc-800/80 bg-zinc-950/60 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-zinc-800">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-zinc-100">
                        Matrix Hak Akses: <span className="text-violet-400">{activeRole.name}</span>
                      </h3>
                      {activeRole.is_system && (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 border border-zinc-700">
                          Role Bawaan Sistem
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400 mt-0.5">{activeRole.description || "Deskripsi role sistem"}</p>
                  </div>

                  <Button size="sm" variant="outline" onClick={() => openEditRole(activeRole)} icon={<Edit3 className="h-3.5 w-3.5" />}>
                    Kelola Hak Akses
                  </Button>
                </div>

                {activeRole.name === "superadmin" ? (
                  <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 text-emerald-300 text-xs flex items-start gap-3">
                    <Sparkles className="h-4 w-4 shrink-0 mt-0.5 text-emerald-400" />
                    <div>
                      <p className="font-semibold text-emerald-200">Akses Penuh Tanpa Batasan (Superadmin Bypass)</p>
                      <p className="text-emerald-300/80 mt-0.5">
                        Role superadmin memiliki hak penuh atas seluruh endpoint, konfigurasi database, model AI, dan aksi sistem tanpa perlu konfigurasi permission manual.
                      </p>
                    </div>
                  </div>
                ) : null}

                {/* Categorized permissions display */}
                <div className="space-y-4 max-h-[500px] overflow-y-auto pr-1">
                  {Object.entries(permissionsGrouped).map(([category, perms]) => {
                    const activeCodes = new Set(activeRole.permissions.map((p) => p.code));
                    const isFullSuper = activeRole.name === "superadmin";

                    return (
                      <div key={category} className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-3 space-y-2">
                        <div className="flex items-center justify-between pb-1.5 border-b border-zinc-800/60">
                          <span className="text-xs font-semibold text-zinc-300">
                            {categoryLabels[category] || category}
                          </span>
                          <span className="text-[10px] text-zinc-500">
                            {isFullSuper
                              ? `${perms.length}/${perms.length} Aktif`
                              : `${perms.filter((p) => activeCodes.has(p.code)).length}/${perms.length} Aktif`}
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                          {perms.map((p) => {
                            const isGranted = isFullSuper || activeCodes.has(p.code);
                            return (
                              <div
                                key={p.id}
                                className={cn(
                                  "flex items-start gap-2.5 p-2 rounded-lg border text-left text-xs transition-colors",
                                  isGranted
                                    ? "border-emerald-500/30 bg-emerald-500/5 text-zinc-200"
                                    : "border-zinc-800/50 bg-zinc-950/40 text-zinc-500 opacity-60"
                                )}
                              >
                                <div className="mt-0.5">
                                  {isGranted ? (
                                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                                  ) : (
                                    <X className="h-3.5 w-3.5 text-zinc-600" />
                                  )}
                                </div>
                                <div className="min-w-0">
                                  <p className="font-medium text-[11px] text-zinc-200 truncate">{p.name}</p>
                                  <p className="text-[10px] font-mono text-zinc-400 truncate">{p.code}</p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            ) : (
              <div className="p-8 text-center text-xs text-zinc-500">Pilih salah satu role untuk melihat matrix hak akses.</div>
            )}
          </div>
        </div>
      )}

      {/* ─── MODAL: ADD / EDIT USER ───────────────────────────────────────────── */}
      <Modal
        open={showAddUserModal || editingUser !== null}
        onClose={() => {
          setShowAddUserModal(false);
          setEditingUser(null);
        }}
        title={editingUser ? `Edit Pengguna: ${editingUser.email}` : "Tambah Pengguna Baru"}
      >
        <div className="space-y-4">
          <Input
            label="Email Pengguna"
            type="email"
            value={formEmail}
            onChange={(e) => setFormEmail(e.target.value)}
            disabled={editingUser !== null}
            placeholder="nama@domain.com"
          />

          <Input
            label="Nama Lengkap"
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="John Doe"
          />

          <Input
            label={editingUser ? "Kata Sandi Baru (Opsional)" : "Kata Sandi"}
            type="password"
            value={formPassword}
            onChange={(e) => setFormPassword(e.target.value)}
            placeholder={editingUser ? "Biarkan kosong jika tidak diubah" : "Minimal 6 karakter"}
          />

          <div>
            <label className="block text-xs font-medium text-zinc-300 mb-1.5">Role Sistem</label>
            <select
              value={formRoleId}
              onChange={(e) => setFormRoleId(Number(e.target.value))}
              className="w-full bg-zinc-950/80 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-violet-500/50"
            >
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} — {r.description || (r.is_system ? "System Role" : "Custom Role")}
                </option>
              ))}
            </select>
          </div>

          <div className="pt-2 border-t border-zinc-800/80 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-zinc-200">Akses Fitur Premium</p>
                <p className="text-[10px] text-zinc-500">Pipeline V1 Gemini, Auto Grid, Three.js, AI Layer</p>
              </div>
              <button
                type="button"
                onClick={() => setFormIsPremium(!formIsPremium)}
                className={cn(
                  "w-10 h-5 rounded-full transition-colors relative",
                  formIsPremium ? "bg-amber-500" : "bg-zinc-700"
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                    formIsPremium && "translate-x-5"
                  )}
                />
              </button>
            </div>

            {editingUser && (
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-zinc-200">Status Akun Aktif</p>
                  <p className="text-[10px] text-zinc-500">Jika dinonaktifkan, pengguna tidak dapat login</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFormIsActive(!formIsActive)}
                  className={cn(
                    "w-10 h-5 rounded-full transition-colors relative",
                    formIsActive ? "bg-emerald-500" : "bg-zinc-700"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                      formIsActive && "translate-x-5"
                    )}
                  />
                </button>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-zinc-800">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowAddUserModal(false);
                setEditingUser(null);
              }}
            >
              Batal
            </Button>
            <Button
              size="sm"
              loading={isSubmittingUser}
              onClick={editingUser ? handleUpdateUser : handleCreateUser}
            >
              {editingUser ? "Simpan Perubahan" : "Buat Pengguna"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* ─── MODAL: CREATE / EDIT ROLE & PERMISSIONS ──────────────────────────── */}
      <Modal
        open={showRoleModal}
        onClose={() => setShowRoleModal(false)}
        title={editingRole ? `Edit Role: ${editingRole.name}` : "Buat Role Kustom Baru"}
      >
        <div className="space-y-4">
          <Input
            label="Nama Role (lowercase, huruf/angka/underscore)"
            value={roleName}
            onChange={(e) => setRoleName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
            disabled={editingRole?.is_system}
            placeholder="contoh: content_creator"
          />

          <Input
            label="Deskripsi Role"
            value={roleDescription}
            onChange={(e) => setRoleDescription(e.target.value)}
            placeholder="Deskripsi singkat fungsi role..."
          />

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-zinc-200">Konfigurasi Hak Akses (Permissions)</label>
              <span className="text-[10px] text-zinc-400">
                {selectedPermissionIds.length} hak akses dipilih
              </span>
            </div>

            <div className="space-y-3 max-h-[360px] overflow-y-auto p-2 bg-zinc-950/60 border border-zinc-800 rounded-xl">
              {Object.entries(permissionsGrouped).map(([category, perms]) => {
                const catIds = perms.map((p) => p.id);
                const allSelected = catIds.every((id) => selectedPermissionIds.includes(id));
                const someSelected = catIds.some((id) => selectedPermissionIds.includes(id));

                return (
                  <div key={category} className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 space-y-2">
                    <div className="flex items-center justify-between pb-1 border-b border-zinc-800/60">
                      <span className="text-xs font-medium text-zinc-200">
                        {categoryLabels[category] || category}
                      </span>
                      <button
                        type="button"
                        onClick={() => toggleCategoryPermissions(perms)}
                        className="text-[10px] font-medium text-violet-400 hover:text-violet-300 transition-colors"
                      >
                        {allSelected ? "Batal Semua" : "Pilih Semua"}
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                      {perms.map((p) => {
                        const checked = selectedPermissionIds.includes(p.id);
                        return (
                          <label
                            key={p.id}
                            className={cn(
                              "flex items-start gap-2 p-1.5 rounded-md cursor-pointer text-left transition-colors border",
                              checked
                                ? "bg-violet-500/10 border-violet-500/30 text-zinc-200"
                                : "bg-zinc-950/30 border-transparent text-zinc-400 hover:bg-zinc-900"
                            )}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => togglePermission(p.id)}
                              className="mt-0.5 rounded border-zinc-700 bg-zinc-900 text-violet-500 focus:ring-0"
                            />
                            <div className="min-w-0">
                              <p className="text-[11px] font-medium text-zinc-200 truncate">{p.name}</p>
                              <p className="text-[9px] font-mono text-zinc-500 truncate">{p.code}</p>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-zinc-800">
            <Button variant="outline" size="sm" onClick={() => setShowRoleModal(false)}>
              Batal
            </Button>
            <Button size="sm" loading={isSubmittingRole} onClick={handleSaveRole}>
              {editingRole ? "Simpan Perubahan" : "Buat Role"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
