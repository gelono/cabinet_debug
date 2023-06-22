var lang_start_link = '/' + document.documentElement.lang;

window.addEventListener("DOMContentLoaded", () => {
    if (document.querySelector("#permissions_form"))
        saveRadio();
    if (document.querySelector(".table_projects"))
        tableProjectsDclick();
    if (document.querySelector(".objects-items"))
        tableObjectsDclick();
    if (document.querySelector(".slide_membership_listener"))
        slideMembershipListener();
    if (document.querySelector(".modal-link"))
        saveLink();
    if (document.querySelector(".search")){
        if (window.location.search){
            document.querySelector('.search button').click()
//            console.log(window.location.search)
            document.querySelector('.search input').value = decodeURI(window.location.search.replace('?s=', ''))
            $(".search input").focus();
        }
        realSearch();
    }
    if (document.querySelector(".menu-holder"))
        menuBottomClick();
    if (document.querySelector(".form-share"))
        shareClick('.form-share');
    if (document.querySelector("#invitation_form"))
        shareClick('#invitation_form');
    if (document.querySelector("#members_email_invite")){
        membersEmailType();
        membersSearch();
    }
    if (document.querySelector(".ajax-validation"))
        validateForms();
    if (document.querySelector("#file"))
        validateFileUpload();
    if (document.querySelector("#clearCacheForm"))
        clearCacheHandler();
    if (document.querySelector(".vm-table"))
        runVmHandler();
    if (document.querySelector("#langForm"))
        submitLang();
    if (document.querySelector("#reference-search"))
        referenceSearch();
    if (document.querySelector(".has-preview"))
        previewDclick();
});


function saveRadio(){
    const role = document.querySelector('form[name=role]');

    role.addEventListener("change", function (e) {
        // Получаем данные из формы
        let data = new FormData(this);
        fetch(`${this.action}`, {
            method: 'POST',
            body: data
        })
            .catch(error => alert("Error"))
    });
};


function tableProjectsDclick(){
    let tableRows = document.getElementsByClassName("table-row");

    for (let i=0; i< tableRows.length; i++){
        let row = tableRows[i];
        row.addEventListener('dblclick', function(e){
//            document.location.href = lang_start_link + '/projects/'+ row.getAttribute("data-id")
            document.location.href = `${lang_start_link}/projects/${row.getAttribute("data-id")}`
        });
    }
}

function previewDclick(){
    let tableRows = document.getElementsByClassName("has-preview");

    for (let i=0; i< tableRows.length; i++){
        let row = tableRows[i];
        row.addEventListener('dblclick', function(e){
//            var url = lang_start_link + '/file/'+ row.getAttribute("data-id") + '/preview/'
            var url = `${lang_start_link}/file/${row.getAttribute("data-id")}/preview/`
            window.open(url);
        });
    }
}

function tableObjectsDclick(){
    let tableRows = document.getElementsByClassName("folder-row");

    for (let i=0; i< tableRows.length; i++){
        let row = tableRows[i];
        row.addEventListener('dblclick', function(e){
//            var start = lang_start_link + '/projects/';
            var start = `${lang_start_link}/projects/`;
//            var adr = document.querySelector("#project_id").value + '/' + row.getAttribute("data-id");
            var adr = `${document.querySelector("#project_id").value}/${row.getAttribute("data-id")}`;
            document.location.href = start + adr;
        });
    }
}

function slideMembershipListener(){
    let selectors = document.getElementsByClassName("slide_membership_listener");

    for (let i=0; i< selectors.length; i++){
        let selector = selectors[i];
        selector.addEventListener('change', function(e){
            let data = new FormData(this);
            fetch(`${this.action}`, {
                method: 'POST',
                body: data
            })
            .then(response => location.reload())
            .catch(error => alert("Error"))
        });
    }
}


function saveLink(){
    var pub_link = document.querySelector('#load_link_form');


    pub_link.addEventListener("change", function (e) {
        e.preventDefault();
        let data;

        var pub_check = this.querySelector("#slideOne");
        var share_check = this.querySelector("#slideTwo");

        if (e.target.id == "slideOne"){
            if (!e.target.checked && share_check){
                share_check.checked = false;
                $(share_check.closest('.slideOne')).removeClass('checked');
            }
            form = this.querySelector('form[name=pub_link]');
            data = new FormData(form);

//            if ($(pub_check.querySelector('input')).prop("checked")) {
//                console.log(true);
////                $(".slideTwo").addClass('checked');
//            } else {
//                console.log($(pub_check.querySelector('input')).prop("checked"));
//                console.log(share_check);
//                share_check.input.checked = false;
//                console.log($(pub_check.querySelector('input')).prop("checked"));
////                $(this).closest('.slideOne').removeClass('checked');
//            }
        }else{
            if (e.target.checked){
                pub_check.checked = true;
                $(pub_check.closest('.slideOne')).addClass('checked');
            }
            form = this.querySelector('form[name=all_files_shared]');
            data = new FormData(form);
            data.append('all_files_shared_checkbox', 'True')
            if (this.querySelector('.slideOne').classList.contains('checked'))
                data.append('is_public', 'True');
        }

        fetch(`${form.action}`, {
            method: 'POST',
            body: data
        })
            .catch(error => alert("Error"))
    });

};


function realSearch(){
    var searchInput = document.querySelector('.search input');

    searchInput.oninput = function () {
        var $this = $(this);
        var delay = 500; // 0.5 seconds delay after last input

        clearTimeout($this.data('timer'));
        $this.data('timer', setTimeout(function(){
            $this.removeData('timer');
//            document.location.href = '?s='+ searchInput.value
            document.location.href = `?s=${searchInput.value}`
        }, delay));

    };
};


function referenceSearch(){
    var searchInput = document.querySelector('#reference-search');
    var form = document.querySelector('.form-search');
    var parentDiv = $('.search__result')
    var resetButton =  document.querySelector('.reset');

//    $(document).on('click', '.result-item', function(){
//        document.location.href = this.querySelector('input').value;
//    });
    $(document).on('click', '.reset', function(){
        searchInput.value = '';
        parentDiv.addClass('hide');
        resetButton.style.display = 'none';
        $('.search__result-inner').remove();
        $('.empty-result').remove();
    });

    searchInput.oninput = function () {
        var $this = $(this);
        var delay = 100; // 0.1 seconds delay after last input

        clearTimeout($this.data('timer'));
        $this.data('timer', setTimeout(function(){
            $this.removeData('timer');
            if (searchInput.value){
                console.log(resetButton)
                resetButton.style.display = 'block';
//                var url = $(form).attr('action') + '?s=' + searchInput.value;
                var url = `${$(form).attr('action')}?s=${searchInput.value}`;
                $.ajax({
                    url: url,
                    type: "GET",

                    success: function(data){
                        $('.search__result-inner').remove()
                        $('.empty-result').remove()
                        parentDiv.removeClass('hide');

                        if (data.status == 'ok' ){
                            console.log(data.results);
                            var results = data.results
                            if (!$.isEmptyObject(results)) {
                                let div = document.createElement('div');
                                div.className = "search__result-inner";
                                parentDiv.append(div);
                                for (var key in results) {
                                    console.log(key)
                                    var linkEl = document.createElement('a');
                                    linkEl.href = results[key]['link'];
                                    var innerDiv = document.createElement('div');
                                    innerDiv.className = "result-item";
//                                    innerDiv.innerHTML = '<div class="result-item__title">' + key +
//                                    '</div><div class="result-item__descr">' + results[key]['content'] + '</div>';
                                    innerDiv.innerHTML = `<div class="result-item__title">${key}</div><div class="result-item__descr">${results[key]['content']}</div>`;
                                    linkEl.append(innerDiv);
                                    div.append(linkEl);
                                };
                            } else {
                                let div = document.createElement('div');
                                div.className = "empty-result";
//                                div.innerHTML = '<p>' + gettext('К сожалению, по вашему запросу ничего не найдено.') +
//                                  '</p><p>' + gettext('Введите другой запрос или посмотрите категории.') + '</p>';
                                div.innerHTML = `<p>${gettext('К сожалению, по вашему запросу ничего не найдено.')}</p><p>${gettext('Введите другой запрос или посмотрите категории.')}</p>`;
                                parentDiv.append(div);
                            }
                        } else {
        //                    location.reload()
                            console.log('reload')
                        }
                    }
                });
            } else {
                parentDiv.addClass('hide');
                resetButton.style.display = 'none';
                console.log('clear')
            }
        }, delay));

    };
};

//function slideCheck(){
//    $('.slideOne input').on('click', function () {
//        if ($(this).prop("checked")) {
//            $(this).closest('.slideOne').addClass('checked');
//        } else {
//            $(this).closest('.slideOne').removeClass('checked');
//        }
//      });
//};

function shareClick(form_info){
    const form = document.querySelector(form_info)

    form.addEventListener("submit", function (e) {
        $.post($(form).attr('action'), $(form).serialize(), function(data, textStatus, jqXHR){
                if (data.status == 'error' ){
                    form_name = $(form).attr('name');
                    e.preventDefault();
                    var form_errors = data.errors;
                    for(var fieldname in form_errors) {
                        var errors = form_errors[fieldname];
//                        $('#'+form_name+'-'+fieldname+'-error').get(0).innerHTML = errors;
                        $(`#${form_name}-${fieldname}-error`).get(0).innerHTML = errors;
                    }
                } else {
                    location.reload()
                }
            })
    });
};

function membersEmailType(){
    var mailInput = document.querySelector("#members_email_invite")
    var updButton = document.querySelector("#members_update_button")

    mailInput.oninput = function () {
        if (mailInput.value){
            updButton.setAttribute("form", "invitation_form");
            updButton.innerText = gettext("Добавить участника");
        } else {
            updButton.setAttribute("form", "members_form");
            updButton.innerText = gettext("Обновить");
        }
    }
}

function membersSearch() {
    var searchInput = document.querySelector("#members-search");
    var participantsList = document.querySelector('.participant__list');
    var searchElements = participantsList.querySelectorAll('li .participant__name');
    var searchList = [];

    for (let elem of searchElements) {
        searchList.push(elem.textContent.toLowerCase());
    }

    searchInput.oninput = function () {
        const part_list = participantsList.querySelectorAll('li');
        searchText = searchInput.value.toLowerCase();

        for (let i=0; i< searchList.length; i++){
            if (searchText && !searchList[i].includes(searchText)){
                $(part_list[i]).addClass("hide");
            } else {
                $(part_list[i]).removeClass("hide");
            }
        }

        var part_hide_list = participantsList.querySelectorAll('li.hide');

        if (part_list && (part_list.length != part_hide_list.length)) {
            document.querySelector('.participants__empty').style.display = 'none';
            participantsList.style.display = 'block';
        } else {
            document.querySelector('.participants__empty').style.display = 'block';
            participantsList.style.display = 'none';
        }
    }
}

function validateForms(){
    forms = document.querySelectorAll('.ajax-validation')

    forms.forEach((form) => {
        $(form).submit(function(e) {
            e.preventDefault();
            error_lables = form.querySelectorAll('label.error');
            error_lables.forEach((er_label) => {
                er_label.innerHTML = '';
            })
            $.post($(this).attr('action'), $(this).serialize(), function(data, textStatus, jqXHR){
                if (data.status == 'error' ){
                    form_name = $(form).attr('name');
                    var form_errors = data.errors;
                    for(var fieldname in form_errors) {
                        var errors = form_errors[fieldname];
//                        $('#'+form_name+'-'+fieldname+'-error').get(0).innerHTML = errors;
                        $(`#${form_name}-${fieldname}-error`).get(0).innerHTML = errors;
                    }
                } else if (data.no_redirect == true) {
                    $('.message').addClass('visible');
                    setTimeout(function () {
                      $('.message').removeClass('visible');
                    }, 3000);
                } else {
                    document.location.href = data.success_url;
                }
            })
        })
    })
}

function validateFileUpload(){
    var form = document.querySelector('#file_form')
    var list = document.querySelector('#list');


    $(form).submit(function(e) {
        e.preventDefault();
//        prBar(this);
        error_lables = list.querySelectorAll('label.error');
        error_lables.forEach((er_label) => {
            er_label.innerHTML = '';
        })

        var myData = new FormData(form);
        $.ajax({
            url: $(form).attr('action'),
            type: "POST",
            processData: false,
            contentType: false,
            data: myData,
            success: function(data){
                if (data.status == 'error' ){
                    form_name = $(form).attr('name');
                    e.preventDefault();
                    var form_errors = data.errors;
                    var divs = list.querySelectorAll(".file-info")
                    names_array = []

                    divs.forEach((el) => {
                        d = el.querySelector('div:first-child');
                        if (d.hasAttribute("title")){
                            names_array.push($(d).attr("title"));
                        } else {
                            names_array.push(d.innerHTML);
                        }
                    });

                    names_array.forEach((filename) => {
                        var text = form_errors[filename] || data.uploaded[filename];
                        need_div = divs[names_array.indexOf(filename)]
                        need_div.querySelector('label').innerHTML = text;
                    })
                } else {
                    location.reload()
//                    console.log('reload')
                }
            },
            error: function(response) {
                console.log(response);
            }
        });
    });
}

function clearCacheHandler(){
    form = document.querySelector("#clearCacheForm");

    $(form).submit(function(e) {
        e.preventDefault();

        $.post($(this).attr('action'), $(this).serialize(), function(data, textStatus, jqXHR){
            if (data.status == 'error' ){
                    alert("error");
            } else {
                 alert("ok");
            }
        });
    });
}

function submitLang(){
    var form = document.querySelector("#langForm");

    $(document).on('click', '.languages .select-items', function(){
        var new_lang = this.querySelector('.same-as-selected').innerText.toLowerCase().trim();
        but = document.querySelector('#language_input')
        but.value = new_lang;
//        console.log(form)
        but.click();

    });
//    selector.onchange = function () {
//    console.log(form)
//        form.submit();
}



function runVmHandler(){
    let selectors = document.querySelectorAll(".slideOne");

    for (let i=0; i< selectors.length; i++){
        let selector = selectors[i];
        selector.addEventListener('change', function(e){
            if (this.querySelector('input').checked == false){
                var form = document.querySelector('form[name=vm_stop_form]');
                taskItemInContext = this.closest('tr');
                changeStatusToStop();
            } else {
                var form = document.querySelector('form[name=vm_start_form]');
                taskItemInContext = this.closest('tr');
                changeStatusToStart();
            }
            var vm_id = this.querySelector('input').id.replace('vm', '');

            var data =  new FormData(form);
            data.append('name', vm_id);
            $.ajax({
                url: $(form).attr('action'),
                type: $(form).attr('method'),
                data: data,
                processData: false,
                contentType: false,
            });
        });
    }
}

function gen_password(){
    len = 10
    var password = "";
    var symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!№;%:?*()_+=";
    for (var i = 0; i < len; i++){
        password += symbols.charAt(Math.floor(Math.random() * symbols.length));
    }
    document.querySelector('#password').value = password;
}

function menuBottomClick(){
    let buttons = document.querySelector('.menu-holder__icons').getElementsByTagName("a");

    Array.from(buttons).forEach((but) => {
        but.addEventListener('click', function(e){
            var t_rows = document.getElementsByClassName('table-row active');
            var id_array = [];
            var id_folders = [];
            var id_files = [];

            Array.from(t_rows).forEach((row) => {
                if ($(row).hasClass('folder-row')){
                    id_folders.push(row.getAttribute("data-id"));
                } else {
                    id_files.push(row.getAttribute("data-id"));
                }
                id_array.push(row.getAttribute("data-id"));
            });

            switch (but.getAttribute("data-action")) {
                case "proj_openShare":
                     document.querySelector('#selected_items').value = id_array.join();
                case "proj_getLink":
//                    var redirect = lang_start_link + '/projects/get_link/?pr='+id_array.join();
                    var redirect = `${lang_start_link}/projects/get_link/?pr=${id_array.join()}`;
                    $.ajax({
                        type:"GET",
                        url: redirect,
                        success: function(result){
                            $('#load_link_form').html(result);
                        }
                    });
                    break;
                case "proj_delete":
//                    document.location.href = '/projects/delete/?obj='+ id_array.join();
//                    document.querySelector("#obj_delete_form").action = lang_start_link + '/projects/delete/?obj='+ id_array.join();
                    document.querySelector("#obj_delete_form").action = `${lang_start_link}/projects/delete/?obj=${id_array.join()}`;
                    break;
                case "proj_rename":
//                    if (id_array.length > 1){
//                        id_array.forEach(proj_id => window.open('/projects/' + proj_id + '/rename/'));
//                    } else {
//                        document.location.href = '/projects/' + id_array[0] + '/rename/';
//                    }
//                    document.querySelector(".form-rename-object").action = lang_start_link + '/projects/' + id_array[0] + '/rename/';
                    document.querySelector(".form-rename-object").action = `${lang_start_link}/projects/${id_array[0]}/rename/`;
                    document.querySelector("#obj_rename").value = document.querySelector("#proj_name" + id_array[0]).textContent
                    break;
                case "proj_download":
                    var first_flag = true;
                    var redirect
                    for (var i=0; i < id_array.length; i++){
                        if (first_flag){
//                            redirect = lang_start_link + '/projects/' + id_array[i] + '/download/';
                            redirect = `${lang_start_link}/projects/${id_array[i]}/download/`;
                            if (id_array.length > 1)
                                redirect += "?add=";
                            first_flag = false;
                        }
                        else{
                            redirect += id_array[i];
                            if (i < id_array.length - 1)
                                redirect += ',';
                        }
                    };
                    document.location.href = redirect;
                    break;
                case "obj_openShare":
//                    var redirect = lang_start_link + '/projects/get_link/?pr=' + document.querySelector("#project_id").value;
                    var redirect = `${lang_start_link}/projects/get_link/?pr=${document.querySelector("#project_id").value}`;
                    $.ajax({
                        type:"GET",
                        url: redirect,
                        success: function(result){
                            $('#load_link_form').html(result);
                        }
                    });
                    break;
                case "obj_getLink":
//                    var redirect = lang_start_link + '/projects/file/get_link/?obj=' + id_array.join();
//                    var adr = lang_start_link + '/projects/file/get_link/?';
                    var adr = `${lang_start_link}/projects/file/get_link/?`;
//                    var objects = 'obj=' + id_files.join();
                    var objects = `obj=${id_files.join()}`;
//                    var folders = 'dir=' + id_folders.join();
                    var folders = `dir=${id_folders.join()}`;

                    if (id_files.length != 0 && id_folders.length != 0){
                        adr += objects + '&' + folders;
                    } else if (id_files.length != 0) {
                        adr += objects;
                    } else if (id_folders.length != 0) {
                        adr += folders;
                    }

                    $.ajax({
                        type:"GET",
                        url: adr,
                        success: function(result){
                            $('#load_link_form').html(result);
                        }
                    });
                    break;
                case "obj_delete":
//                    document.location.href = window.location.pathname + 'delete/?obj='+ id_array.join();
//                    var start = lang_start_link + '/projects/';
                    var start = `${lang_start_link}/projects/`;
//                    var objects = 'obj=' + id_files.join();
                    var objects = `obj=${id_files.join()}`;
//                    var folders = 'dir=' + id_folders.join();
                    var folders = `dir=${id_folders.join()}`;
//                    var adr = document.querySelector("#project_id").value + '/delete/?';
                    var adr = `${document.querySelector("#project_id").value}/delete/?`;
                    if (id_files.length != 0 && id_folders.length != 0){
                        adr += objects + '&' + folders;
                    } else if (id_files.length != 0) {
                        adr += objects;
                    } else if (id_folders.length != 0) {
                        adr += folders;
                    }
                    document.querySelector("#obj_delete_form").action = start + adr;
                    break;
                case "obj_rename":
//                    if (id_array.length > 1){
//                        id_array.forEach(obj_id => window.open('/projects/file/' + obj_id + '/rename/'));
//                    } else {
//                        document.location.href = '/projects/file/' + id_array[0] + '/rename/';
//                    }

                    var taskId = id_array[0];
                    console.log($(t_rows[0]).hasClass('folder-row'));
                    if ($(t_rows[0]).hasClass('folder-row')){
//                        document.querySelector(".form-rename-object").action = lang_start_link + '/projects/folder/' + taskId + '/rename/';
                        document.querySelector(".form-rename-object").action = `${lang_start_link}/projects/folder/${taskId}/rename/`;
                        document.querySelector("#obj_rename").value = document.querySelector("#obj_name" + taskId).textContent
                    } else {
//                        document.querySelector(".form-rename-object").action = lang_start_link + '/projects/file/' + taskId + '/rename/';
                        document.querySelector(".form-rename-object").action = `${lang_start_link}/projects/file/${taskId}/rename/`;
                        document.querySelector("#obj_rename").value = document.querySelector("#obj_name" + taskId).textContent
                    }
                    break;
                case "obj_download":
                    var proj = document.querySelector("#project_id").value
//                    var adr = lang_start_link + '/projects/download/' + proj + '/';
                    var adr = `${lang_start_link}/projects/download/${proj}/`;
                    if (document.querySelector("#folder_id").value != "" && !(window.location.search))
                        adr += document.querySelector("#folder_id").value + '/'
                    adr += '?';

//                    var objects = 'obj=' + id_files.join();
                    var objects = `obj=${id_files.join()}`;
//                    var folders = 'dir=' + id_folders.join();
                    var folders = `dir=${id_folders.join()}`;

                    if (id_files.length != 0 && id_folders.length != 0){
                        adr += objects + '&' + folders;
                    } else if (id_files.length != 0) {
                        adr += objects;
                    } else if (id_folders.length != 0) {
                        adr += folders;
                    }
                    document.location.href = adr;
                    break;
                case "eml_transfer":
                    // document.querySelector(".form-rename-object").action = lang_start_link + '/projects/' + id_array[0] + '/rename/';
                    // document.querySelector("#obj_rename").value = document.querySelector("#proj_name" + id_array[0]).textContent
//                    var adr = lang_start_link + '/eml/transfer/?';
                    var adr = `${lang_start_link}/eml/transfer/?`;
//                    var project_id = 'project_id=' + document.querySelector("#project_id").value;
                    var project_id = `project_id=${document.querySelector("#project_id").value}`;
//                    var folder_id = 'folder_id=' + document.querySelector("#folder_id").value;
                    var folder_id = `folder_id=${document.querySelector("#folder_id").value}`;

                    adr += project_id + '&' + folder_id;
                    document.location.href = adr;

                    // $.ajax({
                    //     type:"GET",
                    //     url: adr,
                    //     success: function(result){
                    //         $('#load_link_form').html(result);
                    //     }
                    // });
                    break;
            };
        });
    });
}


function gen_uuid() {
    var uuid = ""
    for (var i=0; i < 32; i++) {
        uuid += Math.floor(Math.random() * 16).toString(16);
    }
    return uuid
}


// Add upload progress for multipart forms.
function prBar(form){
        /*
        This throws a syntax error...
        $('form[@enctype=multipart/form-data]').submit(function(){
        */

    // Prevent multiple submits
    if ($.data(form, 'submitted')) return false;



    var freq = 1000; // freqency of update in ms
    var uuid = gen_uuid(); // id for this upload so we can fetch progress info.
    var progress_url = '/upload_progress/'; // ajax view serving progress info



    // Append X-Progress-ID uuid form action
//    form.action += (form.action.indexOf('?') == -1 ? '?' : '&') + 'X-Progress-ID=' + uuid;
    form.action += `${(form.action.indexOf('?') == -1 ? '?' : '&')}X-Progress-ID=${uuid}`;



    var $progress = $('<div id="upload-progress" class="upload-progress"></div>').
        appendTo(document.body).append('<div class="progress-container"><span class="progress-info">uploading 0%</span><div class="progress-bar"></div></div>');



    // progress bar position
    $progress.css({
//            position: ($.browser.msie && $.browser.version < 7 )? 'absolute' : 'fixed',
        zIndex: 3,
        position: 'absolute',
        left: '50%', marginLeft: 0-($progress.width()/2), bottom: '20%'
    }).show();



    // Update progress bar
    function update_progress_info() {
        $progress.show();
        $.getJSON(progress_url, {'X-Progress-ID': uuid}, function(data, status){
            if (data) {
                var progress = parseInt(data.uploaded) / parseInt(data.length);
                var width = $progress.find('.progress-container').width()
                var progress_width = width * progress;
                $progress.find('.progress-bar').width(progress_width);
//                $progress.find('.progress-info').text('uploading ' + parseInt(progress*100) + '%');
                $progress.find('.progress-info').text(`uploading ${parseInt(progress*100)}%)`;
                if (progress >= 1)
                    return;
            }
            window.setTimeout(update_progress_info, freq);
        });
    };
    window.setTimeout(update_progress_info, freq);



    $.data(form, 'submitted', true); // mark form as submitted.
}




function askVmForIp(tableRow){
    // повторить с интервалом 10 секунд
    let timerId = setInterval(checkWork, 10000);
    let IpCellId = 7

    function checkWork(){
        if(tableRow){
            $.ajax({
                type: 'GET',
//                url: lang_start_link + '/vm/getstatus/' + $(tableRow).data('id')+'?asdfasdSDAVXCztete4wA4213423$@!%xcvzdawdgsdFDSFJV',
                url: `${lang_start_link}/vm/getstatus/${$(tableRow).data('id')}?asdfasdSDAVXCztete4wA4213423$@!%xcvzdawdgsdFDSFJV`,
                success: function(data) {
                    console.log(data)
                    if(data.hasOwnProperty('status')){
                        if((data['status'])=='ok' && data['ip']!==''){
                            $(tableRow.cells[IpCellId]).html(data['ip']);
//                            $(el).find('.vm-status').removeClass('vm-status--stop').addClass('vm-status--start');
//                            $(el).find('.status_txt').html('Запущена');
                            clearInterval(timerId);
                        }   else {
                            console.log('no ip');
                            $(tableRow.cells[IpCellId]).html('-');
    //                        $(el).find('.vm-status').removeClass('vm-status--start').addClass('vm-status--stop');
    //                        $(el).find('.status_txt').html('Остановлена');
                        }
                    }

                },
                error: function (xhr, ajaxOptions, thrownError) {
                    console.log('error', xhr.status);
//                    $(el).find('.vm-status').removeClass('vm-status--start').addClass('vm-status--stop');
//                    $(el).find('.status_txt').html('Остановлена');
                },
            });

        } else { console.log('row not selected')}
    };


    // остановить вывод через 10 секунд
//    setTimeout(() => { clearInterval(timerId); console.log('stop'); }, 10000);

}