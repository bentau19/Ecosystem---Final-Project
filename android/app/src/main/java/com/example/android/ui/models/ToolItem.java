package com.example.android.ui.models;

public class ToolItem {
    private String title;
    private int iconRes;
    private String id;
    private boolean enabled;

    public ToolItem(String id, String title, int iconRes) {
        this.id = id;
        this.title = title;
        this.iconRes = iconRes;
        this.enabled = true;
    }

    public String getTitle() { return title; }
    public int getIconRes() { return iconRes; }
    public String getId() { return id; }
    public boolean isEnabled() { return enabled; }

    public void setTitle(String title) { this.title = title; }
    public void setIconRes(int iconRes) { this.iconRes = iconRes; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
