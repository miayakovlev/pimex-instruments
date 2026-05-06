# Подготовка «голой» Linux-виртуалки под spimex-instruments

Краткий чеклист того, что должно быть на **чистой** установке Linux **до** клонирования репозитория и шагов из [INSTALL.md](INSTALL.md).

## Что понадобится с хоста

- **Исходящий HTTPS** до `https://spimex.com` (и к `github.com`, если клонируете оттуда).
- Для отправки CSV по почте — **исходящий SMTP** до вашего почтового сервера (порты обычно **587** или **465**), без блокировки файрволом.

## Образ и пользователь

- Подойдёт минимальный серверный образ: **Debian**, **Ubuntu Server**, **AlmaLinux / Rocky / RHEL**, **Fedora Server** и т.п.
- Рабочий пользователь с **sudo** (или доступ **root**) для установки пакетов.
- SSH по ключу — по желанию; для самого скрипта графическая сессия не нужна.

## Пакеты операционной системы

Скрипт — **Python 3.9+**, зависимости ставятся в **виртуальное окружение** (`venv`). На ОС нужны только базовые инструменты.

### Сначала: какой менеджер пакетов у системы?

Команды из инструкций для **Fedora/RHEL** (`dnf`), **CentOS** (`yum`), **openSUSE** (`zypper`) **не работают** на **Debian/Ubuntu** — там свой менеджер. Перед установкой имеет смысл посмотреть дистрибутив и то, какие программы уже есть:

```bash
cat /etc/os-release
command -v apt apt-get apk pacman yum dnf microdnf zypper 2>/dev/null
```

- если в выводе есть **`apt`** или **`apt-get`** — используйте подраздел **Debian/Ubuntu** ниже (это самый частый случай при ошибках вида `dnf: command not found`);
- если есть **`apk`** — **Alpine**;
- если **`pacman`** — **Arch** / производные.

**Если нет ни `apt`, ни `apk`, ни `pacman`, ни rpm‑семейства** — возможно образ вроде **NixOS**, **Gentoo** или урезанный контейнер: смотрите документацию образа или поставьте обычный серверный **Ubuntu LTS / Debian** / **AlmaLinux**, где известны команды ниже.

### Debian / Ubuntu (`apt`)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git ca-certificates
```

Если команды `apt` нет, но есть только **`apt-get`** (минимальный контейнер):

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git ca-certificates
```

Проверка версии Python:

```bash
python3 --version   # должно быть 3.9 или новее
```

### Alpine Linux (`apk`)

```bash
sudo apk add python3 py3-pip git ca-certificates
```

Если позже `python3 -m venv` пожалуется на отсутствие модуля, доустановите пакет виртуальных окружений для вашей версии Alpine (имя может быть **`py3-virtualenv`** или **`python3-dev`** — см. сообщение об ошибке / wiki Alpine).

### Arch Linux (`pacman`)

```bash
sudo pacman -Syu --needed --noconfirm python python-pip git ca-certificates
```

### Fedora / RHEL 8+ / AlmaLinux / Rocky — `dnf`

```bash
sudo dnf install -y python3 python3-pip git ca-certificates
```

При необходимости на RHEL включите модуль Python (`dnf module enable python39` и т.п.) — главное, чтобы `python3` был **≥ 3.9`.

### CentOS 7 / старый RHEL с `yum` (без `dnf`)

```bash
sudo yum install -y python3 python3-pip git ca-certificates
```

На CentOS 7 штатный `python3` может быть **3.6** — для проекта нужен **3.9+** (отдельный пакет из SCL/IUS или сборка Python; проще поднять ВМ на **AlmaLinux 8+/9+** или **Ubuntu 22.04 LTS**).

### Минимальный образ с `microdnf` (контейнеры UBI и т.п.)

```bash
sudo microdnf install -y python3 python3-pip git ca-certificates
```

### openSUSE (zypper)

```bash
sudo zypper install -y python3 python3-pip git ca-certificates
```

## Часовой пояс и время

Расписание в проекте завязано на **13:20 по Москве** ([INSTALL.md](INSTALL.md), systemd timer). Чтобы локальное время на ВМ совпадало с ожиданиями и логи были читаемы:

```bash
# пример для Europe/Moscow (Debian/Ubuntu)
sudo timedatectl set-timezone Europe/Moscow
timedatectl
```

Если часовой пояс оставите другим, это не ломает выгрузку, но время срабатывания таймера в логах будет в выбранной зоне (в unit по-прежнему может быть указана Moscow — смотрите `systemd/spimex-daily.timer`).

## Сеть и прокси

- Если доступ в интернет только через **HTTP(S)_proxy**, задайте переменные окружения (`https_proxy`, `http_proxy`) для пользователя, от которого запускается cron/systemd-служба, либо в unit-файле / обёртке.
- Корпоративные TLS-прокси с подменой сертификата: может понадобиться доверенный корневой сертификат в системное хранилище (иначе `requests` выдаст ошибки SSL).

## Безопасность и минимальные права

- Откройте во входящем фаерволе только то, что нужно (чаще всего **SSH**). Исходящие соединения к spimex и SMTP должны быть разрешены.
- Каталог с проектом и файл **`.env`** лучше ограничить одним пользователем (`chmod 600` на `.env` — см. [INSTALL.md](INSTALL.md)).

## Дальнейшие шаги

После подготовки ОС переходите к установке приложения: клонирование, `venv`, `requirements.txt`, `urls.txt`, `.env`, пробный запуск и таймер — всё по инструкции **[INSTALL.md](INSTALL.md)**.

## Опционально: запасной режим с браузером

Если когда-нибудь понадобится **Playwright** (`--browser` / `--browser-fallback`), на сервере обычно ставят зависимости Chromium (имя пакета зависит от дистрибутива). До такой необходимости можно не ставать ничего лишнего — для текущих карточек SPIMEX достаточно `requests` и `beautifulsoup4` из [requirements.txt](requirements.txt).
