from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect
)

import os
import uuid

import psycopg2

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename


app = Flask(__name__)

app.secret_key = "my_blog_secret_key"


# =========================================================
# FILE UPLOAD SETTINGS
# =========================================================

UPLOAD_FOLDER = os.path.join(
    "static",
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():

    connection = psycopg2.connect(
        host="localhost",
        port=5173,
        database="blog_db",
        user="postgres",
        password="9021788377"
    )

    return connection


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            blogs.created_at,
            blogs.category,
            blogs.image,
            COUNT(DISTINCT blog_likes.like_id)
                AS like_count,
            COUNT(DISTINCT comments.comment_id)
                AS comment_count
        FROM blogs

        LEFT JOIN users
        ON blogs.author_id = users.user_id

        LEFT JOIN blog_likes
        ON blogs.blog_id = blog_likes.blog_id

        LEFT JOIN comments
        ON blogs.blog_id = comments.blog_id

        GROUP BY
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            blogs.created_at,
            blogs.category,
            blogs.image

        ORDER BY blogs.blog_id DESC

        LIMIT 3;
        """
    )

    latest_blogs = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "index.html",
        latest_blogs=latest_blogs
    )


# =========================================================
# ABOUT
# =========================================================

@app.route("/about")
def about():

    return render_template(
        "about.html"
    )


# =========================================================
# ALL BLOGS
# =========================================================

@app.route("/blogs")
def blogs():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    sort = request.args.get(
        "sort",
        "newest"
    ).strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            users.user_id,
            blogs.created_at,
            blogs.category,
            blogs.image,
            COUNT(DISTINCT blog_likes.like_id)
                AS like_count,
            COUNT(DISTINCT comments.comment_id)
                AS comment_count,
            COUNT(DISTINCT blog_bookmarks.bookmark_id)
                AS bookmark_count
        FROM blogs

        LEFT JOIN users
        ON blogs.author_id = users.user_id

        LEFT JOIN blog_likes
        ON blogs.blog_id = blog_likes.blog_id

        LEFT JOIN comments
        ON blogs.blog_id = comments.blog_id

        LEFT JOIN blog_bookmarks
        ON blogs.blog_id = blog_bookmarks.blog_id

        WHERE 1=1
    """

    parameters = []

    # -----------------------------------------
    # Search
    # -----------------------------------------

    if search:

        query += """
            AND (
                blogs.title ILIKE %s
                OR blogs.content ILIKE %s
                OR users.username ILIKE %s
            )
        """

        search_value = f"%{search}%"

        parameters.append(search_value)
        parameters.append(search_value)
        parameters.append(search_value)

    # -----------------------------------------
    # Category
    # -----------------------------------------

    if category:

        query += """
            AND blogs.category = %s
        """

        parameters.append(category)

    # -----------------------------------------
    # Group By
    # -----------------------------------------

    query += """
        GROUP BY
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            users.user_id,
            blogs.created_at,
            blogs.category,
            blogs.image
    """

    # -----------------------------------------
    # Sorting
    # -----------------------------------------

    if sort == "oldest":

        query += """
            ORDER BY blogs.created_at ASC;
        """

    elif sort == "popular":

        query += """
            ORDER BY like_count DESC,
                     blogs.created_at DESC;
        """

    elif sort == "most-commented":

        query += """
            ORDER BY comment_count DESC,
                     blogs.created_at DESC;
        """

    else:

        query += """
            ORDER BY blogs.created_at DESC;
        """

    cursor.execute(
        query,
        parameters
    )

    blogs = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "blogs.html",
        blogs=blogs,
        search=search,
        category=category,
        sort=sort
    )


# =========================================================

# BLOG DETAIL
# =========================================================

@app.route("/blog/<int:blog_id>")
def blog_detail(blog_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    # -----------------------------------------
    # Blog
    # -----------------------------------------

    cursor.execute(
        """
        SELECT
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            users.user_id,
            users.profile_pic,
            blogs.created_at,
            blogs.category,
            blogs.image
        FROM blogs

        LEFT JOIN users
        ON blogs.author_id = users.user_id

        WHERE blogs.blog_id = %s;
        """,
        (blog_id,)
    )

    blog = cursor.fetchone()

    if blog is None:

        cursor.close()
        connection.close()

        return "Blog not found.", 404

    # -----------------------------------------
    # Like count
    # -----------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM blog_likes
        WHERE blog_id = %s;
        """,
        (blog_id,)
    )

    like_count = cursor.fetchone()[0]

    # -----------------------------------------
    # Current user's like
    # -----------------------------------------

    user_liked = False

    if "user_id" in session:

        cursor.execute(
            """
            SELECT like_id
            FROM blog_likes
            WHERE blog_id = %s
            AND user_id = %s;
            """,
            (
                blog_id,
                session["user_id"]
            )
        )

        user_liked = (
            cursor.fetchone() is not None
        )

    # -----------------------------------------
    # Bookmark status
    # -----------------------------------------

    user_bookmarked = False

    if "user_id" in session:

        cursor.execute(
            """
            SELECT bookmark_id
            FROM blog_bookmarks
            WHERE blog_id = %s
            AND user_id = %s;
            """,
            (
                blog_id,
                session["user_id"]
            )
        )

        user_bookmarked = (
            cursor.fetchone() is not None
        )

    # -----------------------------------------
    # Bookmark count
    # -----------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM blog_bookmarks
        WHERE blog_id = %s;
        """,
        (blog_id,)
    )

    bookmark_count = cursor.fetchone()[0]

    # -----------------------------------------
    # Comments
    # -----------------------------------------

    cursor.execute(
        """
        SELECT
            comments.comment_id,
            comments.comment_text,
            users.username,
            comments.created_at,
            comments.user_id
        FROM comments

        LEFT JOIN users
        ON comments.user_id = users.user_id

        WHERE comments.blog_id = %s

        ORDER BY comments.created_at DESC;
        """,
        (blog_id,)
    )

    comments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "blog_detail.html",
        blog=blog,
        comments=comments,
        like_count=like_count,
        user_liked=user_liked,
        user_bookmarked=user_bookmarked,
        bookmark_count=bookmark_count
    )


# =========================================================
# LIKE / UNLIKE
# =========================================================

@app.route(
    "/like-blog/<int:blog_id>",
    methods=["POST"]
)
def like_blog(blog_id):

    if "user_id" not in session:

        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT like_id
        FROM blog_likes

        WHERE blog_id = %s
        AND user_id = %s;
        """,
        (
            blog_id,
            session["user_id"]
        )
    )

    existing_like = cursor.fetchone()

    if existing_like:

        cursor.execute(
            """
            DELETE FROM blog_likes

            WHERE blog_id = %s
            AND user_id = %s;
            """,
            (
                blog_id,
                session["user_id"]
            )
        )

    else:

        cursor.execute(
            """
            INSERT INTO blog_likes
                (
                    blog_id,
                    user_id
                )
            VALUES
                (
                    %s,
                    %s
                );
            """,
            (
                blog_id,
                session["user_id"]
            )
        )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(
        f"/blog/{blog_id}"
    )


# =========================================================
# BOOKMARK / REMOVE BOOKMARK
# =========================================================

@app.route(
    "/bookmark-blog/<int:blog_id>",
    methods=["POST"]
)
def bookmark_blog(blog_id):

    if "user_id" not in session:

        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT bookmark_id
        FROM blog_bookmarks
        WHERE blog_id = %s
        AND user_id = %s;
        """,
        (
            blog_id,
            session["user_id"]
        )
    )

    existing_bookmark = cursor.fetchone()

    if existing_bookmark:

        cursor.execute(
            """
            DELETE FROM blog_bookmarks
            WHERE blog_id = %s
            AND user_id = %s;
            """,
            (
                blog_id,
                session["user_id"]
            )
        )

    else:

        cursor.execute(
            """
            INSERT INTO blog_bookmarks
            (
                blog_id,
                user_id
            )
            VALUES
            (
                %s,
                %s
            );
            """,
            (
                blog_id,
                session["user_id"]
            )
        )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(
        f"/blog/{blog_id}"
    )


# =========================================================
# SAVED / BOOKMARKED BLOGS
# =========================================================

@app.route("/bookmarks")
def bookmarks():

    if "user_id" not in session:

        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            users.user_id,
            blogs.created_at,
            blogs.category,
            blogs.image,
            COUNT(DISTINCT blog_likes.like_id)
                AS like_count,
            COUNT(DISTINCT comments.comment_id)
                AS comment_count
        FROM blog_bookmarks

        INNER JOIN blogs
        ON blog_bookmarks.blog_id = blogs.blog_id

        LEFT JOIN users
        ON blogs.author_id = users.user_id

        LEFT JOIN blog_likes
        ON blogs.blog_id = blog_likes.blog_id

        LEFT JOIN comments
        ON blogs.blog_id = comments.blog_id

        WHERE blog_bookmarks.user_id = %s

        GROUP BY
            blogs.blog_id,
            blogs.title,
            blogs.content,
            users.username,
            users.user_id,
            blogs.created_at,
            blogs.category,
            blogs.image,
            blog_bookmarks.created_at

        ORDER BY blog_bookmarks.created_at DESC;
        """,
        (session["user_id"],)
    )

    saved_blogs = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "bookmarks.html",
        blogs=saved_blogs
    )


# =========================================================

# COMMENTS
# =========================================================

@app.route(
    "/blog/<int:blog_id>/comment",
    methods=["POST"]
)
def add_comment(blog_id):

    if "user_id" not in session:

        return redirect("/login")

    comment_text = request.form[
        "comment"
    ].strip()

    if not comment_text:

        return redirect(
            f"/blog/{blog_id}"
        )

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO comments
            (
                blog_id,
                user_id,
                comment_text
            )
        VALUES
            (
                %s,
                %s,
                %s
            );
        """,
        (
            blog_id,
            session["user_id"],
            comment_text
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(
        f"/blog/{blog_id}"
    )


# =========================================================
# DELETE COMMENT
# =========================================================

@app.route(
    "/delete-comment/<int:comment_id>",
    methods=["POST"]
)
def delete_comment(comment_id):

    if "user_id" not in session:

        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT blog_id
        FROM comments

        WHERE comment_id = %s
        AND user_id = %s;
        """,
        (
            comment_id,
            session["user_id"]
        )
    )

    comment = cursor.fetchone()

    if comment is None:

        cursor.close()
        connection.close()

        return (
            "You are not allowed to delete this comment.",
            403
        )

    blog_id = comment[0]

    cursor.execute(
        """
        DELETE FROM comments

        WHERE comment_id = %s
        AND user_id = %s;
        """,
        (
            comment_id,
            session["user_id"]
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(
        f"/blog/{blog_id}"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form["email"]

        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                user_id,
                username,
                password

            FROM users

            WHERE email = %s;
            """,
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(
            user[2],
            password
        ):

            session["user_id"] = user[0]

            session["username"] = user[1]

            return redirect("/")

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template(
        "login.html"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        username = request.form[
            "username"
        ]

        email = request.form[
            "email"
        ]

        password = request.form[
            "password"
        ]

        if len(password) < 6:

            return render_template(
                "register.html",
                error=(
                    "Password must be at least "
                    "6 characters long."
                )
            )

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE email = %s;
            """,
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()
            connection.close()

            return render_template(
                "register.html",
                error=(
                    "An account with this email "
                    "already exists."
                )
            )

        hashed_password = (
            generate_password_hash(password)
        )

        cursor.execute(
            """
            INSERT INTO users
                (
                    username,
                    email,
                    password
                )
            VALUES
                (
                    %s,
                    %s,
                    %s
                );
            """,
            (
                username,
                email,
                hashed_password
            )
        )

        connection.commit()

        cursor.close()
        connection.close()

        return render_template(
            "login.html",
            success=(
                "Registration successful! "
                "You can now login."
            )
        )

    return render_template(
        "register.html"
    )


# =========================================================
# CREATE BLOG
# =========================================================

@app.route(
    "/create-blog",
    methods=["GET", "POST"]
)
def create_blog():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        title = request.form["title"]
        content = request.form["content"]
        category = request.form["category"]

        # -----------------------------------------
        # Blog image upload
        # -----------------------------------------

        image = None
        uploaded_image = request.files.get("image")

        if uploaded_image and uploaded_image.filename:

            if not allowed_file(uploaded_image.filename):
                return render_template(
                    "create_blog.html",
                    error=(
                        "Only PNG, JPG, JPEG, "
                        "GIF and WEBP images are allowed."
                    )
                )

            original_name = secure_filename(uploaded_image.filename)
            extension = original_name.rsplit(".", 1)[1].lower()
            new_filename = str(uuid.uuid4()) + "." + extension

            uploaded_image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    new_filename
                )
            )
            image = new_filename

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO blogs
                (
                    title,
                    content,
                    author_id,
                    category,
                    image
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                );
            """,
            (
                title,
                content,
                session["user_id"],
                category,
                image
            )
        )

        connection.commit()
        cursor.close()
        connection.close()

        return redirect("/blogs")

    return render_template("create_blog.html")


# =========================================================
# EDIT BLOG
# =========================================================

@app.route(
    "/edit-blog/<int:blog_id>",
    methods=["GET", "POST"]
)
def edit_blog(blog_id):

    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            blog_id,
            title,
            content,
            category,
            image
        FROM blogs
        WHERE blog_id = %s
        AND author_id = %s;
        """,
        (
            blog_id,
            session["user_id"]
        )
    )

    blog = cursor.fetchone()

    if blog is None:
        cursor.close()
        connection.close()
        return "You are not allowed to edit this blog.", 403

    if request.method == "POST":

        title = request.form["title"]
        content = request.form["content"]
        category = request.form["category"]

        current_image = blog[4]
        image = current_image
        uploaded_image = request.files.get("image")

        if uploaded_image and uploaded_image.filename:

            if not allowed_file(uploaded_image.filename):
                cursor.close()
                connection.close()
                return render_template(
                    "edit_blog.html",
                    blog=blog,
                    error=(
                        "Only PNG, JPG, JPEG, "
                        "GIF and WEBP images are allowed."
                    )
                )

            original_name = secure_filename(uploaded_image.filename)
            extension = original_name.rsplit(".", 1)[1].lower()
            new_filename = str(uuid.uuid4()) + "." + extension

            uploaded_image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    new_filename
                )
            )
            image = new_filename

            if current_image:
                old_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    current_image
                )
                if os.path.exists(old_path):
                    os.remove(old_path)

        cursor.execute(
            """
            UPDATE blogs
            SET
                title = %s,
                content = %s,
                category = %s,
                image = %s
            WHERE blog_id = %s
            AND author_id = %s;
            """,
            (
                title,
                content,
                category,
                image,
                blog_id,
                session["user_id"]
            )
        )

        connection.commit()
        cursor.close()
        connection.close()
        return redirect("/blogs")

    cursor.close()
    connection.close()

    return render_template(
        "edit_blog.html",
        blog=blog
    )


# =========================================================
# DELETE BLOG
# =========================================================

@app.route(
    "/delete-blog/<int:blog_id>",
    methods=["POST"]
)
def delete_blog(blog_id):

    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT image
        FROM blogs
        WHERE blog_id = %s
        AND author_id = %s;
        """,
        (
            blog_id,
            session["user_id"]
        )
    )

    blog_to_delete = cursor.fetchone()

    cursor.execute(
        """
        DELETE FROM blogs
        WHERE blog_id = %s
        AND author_id = %s;
        """,
        (
            blog_id,
            session["user_id"]
        )
    )

    if blog_to_delete and blog_to_delete[0]:
        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            blog_to_delete[0]
        )
        if os.path.exists(image_path):
            os.remove(image_path)

    connection.commit()
    cursor.close()
    connection.close()

    return redirect("/blogs")


# =========================================================
# PROFILE
# =========================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
def profile():

    if "user_id" not in session:

        return redirect("/login")

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    # -----------------------------------------
    # Update profile
    # -----------------------------------------

    if request.method == "POST":

        username = request.form[
            "username"
        ].strip()

        email = request.form[
            "email"
        ].strip()

        if not username or not email:

            cursor.close()
            connection.close()

            return redirect("/profile")

        cursor.execute(
            """
            SELECT profile_pic
            FROM users
            WHERE user_id = %s;
            """,
            (user_id,)
        )

        old_profile = cursor.fetchone()

        old_profile_pic = (
            old_profile[0]
            if old_profile
            else None
        )

        profile_pic = old_profile_pic

        uploaded_file = request.files.get(
            "profile_pic"
        )

        if (
            uploaded_file
            and uploaded_file.filename
        ):

            if not allowed_file(
                uploaded_file.filename
            ):

                cursor.close()
                connection.close()

                return render_template(
                    "profile.html",
                    error=(
                        "Only PNG, JPG, JPEG, "
                        "GIF and WEBP images "
                        "are allowed."
                    )
                )

            original_name = secure_filename(
                uploaded_file.filename
            )

            extension = (
                original_name.rsplit(
                    ".",
                    1
                )[1].lower()
            )

            new_filename = (
                str(uuid.uuid4())
                + "."
                + extension
            )

            uploaded_file.save(
                os.path.join(
                    app.config[
                        "UPLOAD_FOLDER"
                    ],
                    new_filename
                )
            )

            profile_pic = new_filename

            if old_profile_pic:

                old_path = os.path.join(
                    app.config[
                        "UPLOAD_FOLDER"
                    ],
                    old_profile_pic
                )

                if os.path.exists(old_path):

                    os.remove(old_path)

        cursor.execute(
            """
            UPDATE users

            SET
                username = %s,
                email = %s,
                profile_pic = %s

            WHERE user_id = %s;
            """,
            (
                username,
                email,
                profile_pic,
                user_id
            )
        )

        connection.commit()

        session["username"] = username

    # -----------------------------------------
    # User
    # -----------------------------------------

    cursor.execute(
        """
        SELECT
            user_id,
            username,
            email,
            profile_pic

        FROM users

        WHERE user_id = %s;
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    # -----------------------------------------
    # User blogs
    # -----------------------------------------

    cursor.execute(
        """
        SELECT
            blogs.blog_id,
            blogs.title,
            blogs.content,
            blogs.category,
            blogs.created_at,
            blogs.image,
            COUNT(DISTINCT blog_likes.like_id)
                AS like_count,
            COUNT(DISTINCT comments.comment_id)
                AS comment_count

        FROM blogs

        LEFT JOIN blog_likes
        ON blogs.blog_id = blog_likes.blog_id

        LEFT JOIN comments
        ON blogs.blog_id = comments.blog_id

        WHERE blogs.author_id = %s

        GROUP BY
            blogs.blog_id,
            blogs.title,
            blogs.content,
            blogs.category,
            blogs.created_at,
            blogs.image

        ORDER BY blogs.created_at DESC;
        """,
        (user_id,)
    )

    user_blogs = cursor.fetchall()

    # -----------------------------------------
    # Total likes
    # -----------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM blog_likes

        INNER JOIN blogs
        ON blog_likes.blog_id = blogs.blog_id

        WHERE blogs.author_id = %s;
        """,
        (user_id,)
    )

    total_likes = cursor.fetchone()[0]

    # -----------------------------------------
    # Total comments
    # -----------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM comments

        INNER JOIN blogs
        ON comments.blog_id = blogs.blog_id

        WHERE blogs.author_id = %s;
        """,
        (user_id,)
    )

    total_comments = cursor.fetchone()[0]

    # -----------------------------------------
    # Saved blogs
    # -----------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM blog_bookmarks

        WHERE user_id = %s;
        """,
        (user_id,)
    )

    total_bookmarks = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        "profile.html",
        user=user,
        user_blogs=user_blogs,
        total_likes=total_likes,
        total_comments=total_comments,
        total_bookmarks=total_bookmarks
    )


# =========================================================
# PUBLIC AUTHOR PROFILE
# =========================================================

@app.route(
    "/author/<int:user_id>"
)
def author_profile(user_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    # -----------------------------------------
    # Author information
    # -----------------------------------------

    cursor.execute(
        """
        SELECT
            user_id,
            username,
            profile_pic
        FROM users
        WHERE user_id = %s;
        """,
        (user_id,)
    )

    author = cursor.fetchone()

    if author is None:

        cursor.close()
        connection.close()

        return "Author not found.", 404

    # -----------------------------------------
    # Author blogs
    # -----------------------------------------

    cursor.execute(
        """
        SELECT
            blogs.blog_id,
            blogs.title,
            blogs.content,
            blogs.category,
            blogs.created_at,
            blogs.image,
            COUNT(DISTINCT blog_likes.like_id)
                AS like_count,
            COUNT(DISTINCT comments.comment_id)
                AS comment_count

        FROM blogs

        LEFT JOIN blog_likes
        ON blogs.blog_id = blog_likes.blog_id

        LEFT JOIN comments
        ON blogs.blog_id = comments.blog_id

        WHERE blogs.author_id = %s

        GROUP BY
            blogs.blog_id,
            blogs.title,
            blogs.content,
            blogs.category,
            blogs.created_at,
            blogs.image

        ORDER BY blogs.created_at DESC;
        """,
        (user_id,)
    )

    author_blogs = cursor.fetchall()

    # -----------------------------------------
    # Statistics
    # -----------------------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM blogs
        WHERE author_id = %s;
        """,
        (user_id,)
    )

    blog_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM blog_likes

        INNER JOIN blogs
        ON blog_likes.blog_id = blogs.blog_id

        WHERE blogs.author_id = %s;
        """,
        (user_id,)
    )

    like_count = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        "author_profile.html",
        author=author,
        author_blogs=author_blogs,
        blog_count=blog_count,
        like_count=like_count
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# TEST DATABASE
# =========================================================

@app.route("/test-db")
def test_db():

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT current_database();"
    )

    database_name = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return (
        "Database connection successful: "
        f"{database_name}"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )