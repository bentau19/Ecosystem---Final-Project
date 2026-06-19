pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://packagecloud.io/arthenica/maven/maven2") }
    }
}

rootProject.name = "android"
include(":app")
include(":tausync-lib")
project(":tausync-lib").projectDir = File(settingsDir, "../TauSync/Tausync_Android/tausync-lib")
