package com.example.android.ui.models;

public class ToolItem {
    private String title;
    private int iconRes;
    private String id;

    public ToolItem(String id, String title, int iconRes) {
        this.id = id;
        this.title = title;
        this.iconRes = iconRes;
    }

    // Getters
    public String getTitle() { return title; }
    public int getIconRes() { return iconRes; }
    public String getId() { return id; }

    public void setTitle(String title) { this.title = title; }
}
